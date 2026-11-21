import test from 'node:test';
import assert from 'node:assert/strict';
import {retrieveArchive} from '../delivery/client.mjs';
import {sha256, PIECE_SIZE, WIRE_LIMIT} from '../delivery/contract.mjs';

// Synthetic identities, bytes, tokens and ephemeral keys only. No network fallback.
const profiles = ['alpha', 'beta'].map((name, index) => ({
  app_id: `fixture.${name}`, bundle_id: `fixture.${name}.app`, team_id: `FIXTURE00${index}`,
  architecture: index ? 'universal' : 'arm64', minimum_macos: index ? '27.0' : '26.0',
  data_schema_version: index + 1, origin: `https://${name}.invalid`,
}));
const toBase64 = bytes => btoa(String.fromCharCode(...bytes));
const json = value => new Response(JSON.stringify(value), {headers: {'Content-Type': 'application/json'}});

async function fixture(profile = profiles[0], size = PIECE_SIZE + 19) {
  const keys = await crypto.subtle.generateKey('Ed25519', true, ['sign', 'verify']);
  const publicKey = toBase64(new Uint8Array(await crypto.subtle.exportKey('raw', keys.publicKey)));
  const records = new Map();
  const makeArtifact = async kind => {
    const bytes = Uint8Array.from({length: size}, (_, i) => (i * 17 + (kind === 'package' ? 3 : 5)) % 251);
    const descriptor = {path: `/v1/apps/${profile.app_id}/releases/fixture-1/${kind}`, size,
      sha256: await sha256(bytes), ed25519_signature: toBase64(new Uint8Array(await crypto.subtle.sign('Ed25519', keys.privateKey, bytes)))};
    const parts = [];
    for (let offset = 0; offset < size; offset += PIECE_SIZE) {
      const piece = bytes.subarray(offset, offset + PIECE_SIZE);
      parts.push({index: parts.length, size: piece.length, sha256: await sha256(piece)});
    }
    const table = {schema: 'private-distribution/artifact-parts/v2', app_id: profile.app_id,
      release_id: 'fixture-1', kind, artifact_sha256: descriptor.sha256, artifact_size: size,
      part_size: PIECE_SIZE, parts};
    records.set(descriptor.path, {bytes, table, descriptor});
    return descriptor;
  };
  const release = {schema: 'private-distribution/release/v1', app_id: profile.app_id,
    bundle_id: profile.bundle_id, team_id: profile.team_id, architecture: profile.architecture,
    minimum_macos: profile.minimum_macos, data_schema_version: profile.data_schema_version,
    channel: 'stable', version: '1.0', build: 1, source_revision: 'a'.repeat(40),
    qualification_id: 'fixture-only', qualified: true,
    archive: await makeArtifact('archive'), first_install: await makeArtifact('package')};
  const calls = [];
  const fetch = async (url, options) => {
    calls.push({url, options});
    assert.equal(options.headers.Authorization, 'Bearer ' + 'A'.repeat(43));
    assert.equal(options.redirect, 'error'); assert.equal(options.credentials, 'omit');
    assert.equal(options.cache, 'no-store'); assert.equal(options.referrerPolicy, 'no-referrer');
    assert.equal(new URL(url).origin, profile.origin);
    const path = new URL(url).pathname;
    if (path === `/v1/apps/${profile.app_id}/channels/stable/manifest`) return json(release);
    for (const [artifactPath, record] of records) {
      if (path === artifactPath + '/parts') return json(record.table);
      const part = record.table.parts.find(p => path === artifactPath + '/parts/' + p.index);
      if (part) return new Response(record.bytes.slice(part.index * PIECE_SIZE, part.index * PIECE_SIZE + part.size), {
        headers: {'Content-Length': String(part.size)},
      });
    }
    throw new Error('Unexpected synthetic request');
  };
  const options = {profile, configuredOrigin: profile.origin, appId: profile.app_id,
    channel: 'stable', role: 'first_install', accessFile: {schema: 'private-distribution/access/v1',
      app_id: profile.app_id, origin: profile.origin, token: 'A'.repeat(43)},
    publicKey, fetch, maxArchiveBytes: size};
  return {options, release, records, calls, fetch};
}

for (const profile of profiles) for (const role of ['first_install', 'update']) {
  test(`verifies ${profile.app_id} ${role} with two pieces and a locally generated signature`, async () => {
    const f = await fixture(profile);
    const result = await retrieveArchive({...f.options, role});
    const expected = f.records.get(f.release[role === 'first_install' ? 'first_install' : 'archive'].path);
    assert.deepEqual(result.bytes, expected.bytes);
    assert.equal(result.descriptor.path, expected.descriptor.path);
    assert.equal(f.calls.length, 4);
    assert.ok(f.calls.every(call => !call.options.signal.aborted));
  });
}

test('rejects crossed products, origin, channel, missing capacity and malformed key before fetch', async () => {
  const f = await fixture();
  for (const patch of [
    {appId: profiles[1].app_id}, {configuredOrigin: profiles[1].origin},
    {accessFile: {...f.options.accessFile, app_id: profiles[1].app_id}},
    {accessFile: {...f.options.accessFile, origin: profiles[1].origin}},
    {channel: 'public'}, {role: 'download'}, {maxArchiveBytes: undefined},
    {maxArchiveBytes: 512 * 1024 * 1024 + 1}, {publicKey: 'invalid'},
  ]) await assert.rejects(retrieveArchive({...f.options, ...patch}));
  assert.equal(f.calls.length, 0);
});

test('rejects a crossed manifest and a crossed or inconsistent parts identity', async () => {
  for (const change of [
    f => { f.release.app_id = profiles[1].app_id; },
    f => { f.release.channel = 'qualification'; },
    f => { f.release.team_id = profiles[1].team_id; },
    f => { f.release.first_install.path = '/v1/apps/fixture.beta/releases/fixture-1/package'; },
    f => { f.release.first_install.path = f.release.first_install.path.replace('fixture-1', 'fixture-2'); },
    f => { f.records.get(f.release.first_install.path).table.app_id = profiles[1].app_id; },
    f => { f.records.get(f.release.first_install.path).table.kind = 'archive'; },
    f => { f.records.get(f.release.first_install.path).table.release_id = 'fixture-2'; },
    f => { f.records.get(f.release.first_install.path).table.parts[0].index = 1; },
  ]) {
    const f = await fixture(); change(f);
    await assert.rejects(retrieveArchive(f.options));
    assert.ok(f.calls.length <= 2);
  }
});

test('rejects an archive above the caller capacity before parts retrieval', async () => {
  const f = await fixture();
  await assert.rejects(retrieveArchive({...f.options, maxArchiveBytes: f.options.maxArchiveBytes - 1}), /capacity/);
  assert.equal(f.calls.length, 1);
});

test('rejects revoked access, unavailable service, redirects and mismatched final URL without fallback', async () => {
  for (const response of [new Response('', {status: 401}), new Response('', {status: 503}),
    {status: 200, redirected: true}, {status: 200, url: 'https://public.invalid/archive'}]) {
    let calls = 0;
    const f = await fixture();
    await assert.rejects(retrieveArchive({...f.options, fetch: async () => { calls++; return response; }}));
    assert.equal(calls, 1);
  }
});

test('bounds streamed metadata, including absent and oversized Content-Length', async () => {
  for (const headers of [{}, {'Content-Length': String(WIRE_LIMIT + 1)}]) {
    const f = await fixture();
    await assert.rejects(retrieveArchive({...f.options,
      fetch: async () => new Response(' '.repeat(WIRE_LIMIT + 1), {headers})}));
  }
});

test('rejects duplicate wire keys and malformed UTF-8', async () => {
  const f = await fixture();
  for (const body of ['{"app_id":"a","app_id":"b"}', new Uint8Array([0xc3, 0x28])]) {
    await assert.rejects(retrieveArchive({...f.options, fetch: async () => new Response(body)}));
  }
});

test('rejects missing, mismatched, truncated, overflowing and corrupt part bodies', async () => {
  for (const mode of ['missing-length', 'wrong-length', 'truncated', 'overflow', 'corrupt']) {
    const f = await fixture();
    const fetch = async (url, options) => {
      if (!url.endsWith('/parts/0')) return f.fetch(url, options);
      const original = f.records.get(f.release.first_install.path).bytes.slice(0, PIECE_SIZE);
      let bytes = original;
      if (mode === 'truncated') bytes = bytes.subarray(0, bytes.length - 1);
      if (mode === 'overflow') bytes = new Uint8Array(PIECE_SIZE + 1);
      if (mode === 'corrupt') bytes[0] ^= 1;
      return new Response(bytes, {headers: mode === 'missing-length' ? {} : {
        'Content-Length': String(mode === 'wrong-length' ? PIECE_SIZE - 1 : PIECE_SIZE),
      }});
    };
    await assert.rejects(retrieveArchive({...f.options, fetch}), /verification/i);
  }
});

test('rejects final hash even when each part hash is internally consistent', async () => {
  const f = await fixture();
  const record = f.records.get(f.release.first_install.path);
  record.descriptor.sha256 = '0'.repeat(64); record.table.artifact_sha256 = record.descriptor.sha256;
  await assert.rejects(retrieveArchive(f.options), /verification/i);
  assert.equal(f.calls.length, 4);
});

test('requires the configured signing key and checks signature after matching hashes', async () => {
  const f = await fixture();
  const other = await fixture(profiles[1], 1);
  await assert.rejects(retrieveArchive({...f.options, publicKey: other.options.publicKey}), /verification/i);
  f.release.first_install.ed25519_signature = toBase64(new Uint8Array(64));
  await assert.rejects(retrieveArchive(f.options), /verification/i);
});

test('whole-archive deadline interrupts a fetch that ignores its abort signal', async () => {
  const f = await fixture();
  await assert.rejects(retrieveArchive({...f.options, deadlineMs: 20,
    fetch: () => new Promise(() => {})}), {name: 'TimeoutError'});
});

test('accepts arbitrary transport chunks without allocating one buffer per piece', async () => {
  const f = await fixture();
  const fetch = async (url, options) => {
    const response = await f.fetch(url, options);
    const bytes = new Uint8Array(await response.arrayBuffer());
    let offset = 0;
    return new Response(new ReadableStream({pull(controller) {
      if (offset === bytes.length) { controller.close(); return; }
      const end = Math.min(offset + 1009, bytes.length);
      controller.enqueue(bytes.subarray(offset, end)); offset = end;
    }}), {headers: response.headers});
  };
  const result = await retrieveArchive({...f.options, fetch});
  assert.deepEqual(result.bytes, f.records.get(f.release.first_install.path).bytes);
});

test('uses one deadline across successive otherwise responsive requests', async () => {
  const f = await fixture(); let calls = 0;
  await assert.rejects(retrieveArchive({...f.options, deadlineMs: 100, fetch: async (url, options) => {
    calls++;
    await new Promise(resolve => setTimeout(resolve, 40));
    return f.fetch(url, options);
  }}), {name: 'TimeoutError'});
  assert.ok(calls > 1 && calls < 4);
  // Let the deliberately signal-ignoring fixture settle before leaving the test.
  await new Promise(resolve => setTimeout(resolve, 50));
});

test('cancels a response body if an aborted signal-ignoring fetch resolves late', async () => {
  const f = await fixture(); const caller = new AbortController();
  let resolveFetch, cancelled = false;
  const promise = retrieveArchive({...f.options, signal: caller.signal, fetch: () => {
    queueMicrotask(() => caller.abort());
    return new Promise(resolve => { resolveFetch = resolve; });
  }});
  await assert.rejects(promise, {name: 'AbortError'});
  resolveFetch(new Response(new ReadableStream({cancel() { cancelled = true; }})));
  await new Promise(resolve => queueMicrotask(resolve));
  assert.equal(cancelled, true);
});

test('caller abort is immediate for a pending fetch and an already-aborted signal', async () => {
  const f = await fixture();
  for (const alreadyAborted of [false, true]) {
    const caller = new AbortController();
    if (alreadyAborted) caller.abort();
    const promise = retrieveArchive({...f.options, signal: caller.signal, fetch: () => {
      queueMicrotask(() => caller.abort()); return new Promise(() => {});
    }});
    await assert.rejects(promise, {name: 'AbortError'});
  }
});

test('abort and deadline cancel an uncooperative pending body reader', async () => {
  for (const callerAbort of [false, true]) {
    const f = await fixture(); const caller = new AbortController(); let cancelled = false;
    await assert.rejects(retrieveArchive({...f.options, signal: caller.signal, deadlineMs: 20,
      fetch: async () => new Response(new ReadableStream({pull() {
        if (callerAbort) queueMicrotask(() => caller.abort());
        return new Promise(() => {});
      }, cancel() { cancelled = true; }}))}), {name: callerAbort ? 'AbortError' : 'TimeoutError'});
    assert.equal(cancelled, true);
  }
});

test('removes caller callbacks on success and failure and clears its success deadline timer', async () => {
  const f = await fixture(profiles[0], 1);
  for (const fails of [false, true]) {
    const caller = new AbortController(); let added = 0, removed = 0;
    const add = caller.signal.addEventListener.bind(caller.signal);
    const remove = caller.signal.removeEventListener.bind(caller.signal);
    caller.signal.addEventListener = (...args) => { added++; return add(...args); };
    caller.signal.removeEventListener = (...args) => { removed++; return remove(...args); };
    const options = {...f.options, signal: caller.signal, deadlineMs: 100,
      ...(fails ? {fetch: async () => new Response('', {status: 503})} : {})};
    if (fails) await assert.rejects(retrieveArchive(options)); else await retrieveArchive(options);
    assert.equal(added, 1); assert.equal(removed, 1);
  }
  await new Promise(resolve => setTimeout(resolve, 120));
  assert.ok(f.calls.every(call => !call.options.signal.aborted));
});
