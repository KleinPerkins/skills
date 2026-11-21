// Adapted from the owner-approved Machine Monitor reference at
// 4f26c15527ef6912434e3953de6169aed8244e28, delivery/web.mjs.
import {origin, access, manifest, pieceDescriptor, parseWireJSON, sha256, WIRE_LIMIT} from './contract.mjs';

const CONTRACT_ARCHIVE_LIMIT = 512 * 1024 * 1024;
const MAX_DEADLINE_MS = 300_000;

function fail(message = 'Archive verification failed') { throw new Error(message); }

function base64Bytes(text, length) {
  if (typeof text !== 'string') fail('Invalid Ed25519 public key');
  let raw;
  try { raw = atob(text); } catch { fail('Invalid base64'); }
  if (raw.length !== length || btoa(raw) !== text) fail('Invalid base64');
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

/**
 * Retrieve authenticated archive bytes without exposing an unverified stream.
 * publicKey is the owner-configured canonical base64 raw 32-byte Ed25519 key.
 * maxArchiveBytes is a mandatory caller-owned memory/capacity ceiling (<=512 MiB).
 * role selects first_install/package or update/archive; there is no fallback.
 * The injected fetch must implement standard Fetch semantics, including signals.
 * WebCrypto can allocate internal copies; budget for more than maxArchiveBytes.
 */
export async function retrieveArchive({profile: suppliedProfile, configuredOrigin, appId, channel,
  role, accessFile, publicKey, fetch: fetchImpl, signal, maxArchiveBytes,
  deadlineMs = MAX_DEADLINE_MS}) {
  const profile = Object.freeze({...suppliedProfile});
  if (typeof fetchImpl !== 'function') fail('An explicit fetch implementation is required');
  if (!Number.isSafeInteger(maxArchiveBytes) || maxArchiveBytes < 1 || maxArchiveBytes > CONTRACT_ARCHIVE_LIMIT)
    fail('Invalid archive capacity');
  if (!Number.isSafeInteger(deadlineMs) || deadlineMs < 1 || deadlineMs > MAX_DEADLINE_MS)
    fail('Invalid archive deadline');
  if (!['stable', 'qualification'].includes(channel) || !['first_install', 'update'].includes(role))
    fail('Invalid channel or artifact role');
  if (typeof appId !== 'string' || appId !== profile.app_id || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(appId))
    fail('Invalid product');
  const base = origin(configuredOrigin);
  if (base !== profile.origin) fail('Origin does not match product profile');
  const credential = access({...accessFile}, profile);
  if (credential.origin !== base) fail('Access origin does not match configuration');
  const keyBytes = base64Bytes(publicKey, 32);
  const controller = new AbortController();
  const deadline = Date.now() + deadlineMs;
  const abortFromCaller = () => controller.abort(signal.reason);
  const timeoutError = () => new DOMException('Archive deadline exceeded', 'TimeoutError');
  const timer = setTimeout(() => controller.abort(timeoutError()), deadlineMs);
  if (signal) {
    signal.addEventListener('abort', abortFromCaller, {once: true});
    if (signal.aborted) abortFromCaller();
  }

  function check() {
    if (!controller.signal.aborted && Date.now() >= deadline) controller.abort(timeoutError());
    controller.signal.throwIfAborted();
  }

  // Race every async operation, including body reads and WebCrypto, so cancellation
  // rejects promptly even when a supplied fetch/stream fails to honor its signal.
  function wait(promise) {
    return new Promise((resolve, reject) => {
      const aborted = () => { cleanup(); reject(controller.signal.reason); };
      const cleanup = () => controller.signal.removeEventListener('abort', aborted);
      controller.signal.addEventListener('abort', aborted, {once: true});
      Promise.resolve(promise).then(value => {
        cleanup();
        try { check(); resolve(value); } catch (error) { reject(error); }
      }, error => { cleanup(); reject(error); });
      if (controller.signal.aborted) aborted();
    });
  }

  async function request(path) {
    check();
    const url = base + path;
    const pending = Promise.resolve(fetchImpl(url, {
      method: 'GET', headers: {Authorization: 'Bearer ' + credential.token},
      signal: controller.signal, redirect: 'error', cache: 'no-store',
      credentials: 'omit', referrerPolicy: 'no-referrer',
    }));
    // If a fetch ignores abort and resolves late, relinquish its response body.
    pending.then(response => {
      if (controller.signal.aborted) response.body?.cancel().catch(() => {});
    }, () => {});
    const response = await wait(pending);
    if (response.status !== 200 || response.redirected || (response.url && response.url !== url)) {
      response.body?.cancel().catch(() => {});
      fail('Private archive request failed');
    }
    if (!response.body || typeof response.body.getReader !== 'function') fail('Missing response body');
    return response;
  }

  async function read(response, target, exact = false) {
    const length = response.headers.get('Content-Length');
    if ((exact && length !== String(target.byteLength)) ||
        (length !== null && (!/^(0|[1-9][0-9]*)$/.test(length) || Number(length) > target.byteLength))) {
      response.body.cancel().catch(() => {});
      fail();
    }
    const reader = response.body.getReader();
    let count = 0, done = false;
    try {
      while (true) {
        check();
        const item = await wait(reader.read());
        if (item.done) { done = true; break; }
        if (!(item.value instanceof Uint8Array) || count + item.value.byteLength > target.byteLength) fail();
        target.set(item.value, count);
        count += item.value.byteLength;
      }
      if ((exact && count !== target.byteLength) || (length !== null && count !== Number(length))) fail();
      return count;
    } finally {
      // Cancellation is best effort; an uncooperative producer cannot hold up abort.
      if (!done) reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function json(path, limit) {
    const bytes = new Uint8Array(limit);
    const count = await read(await request(path), bytes);
    check();
    return parseWireJSON(new TextDecoder('utf-8', {fatal: true}).decode(bytes.subarray(0, count)));
  }

  try {
    check();
    const key = await wait(crypto.subtle.importKey('raw', keyBytes, 'Ed25519', false, ['verify']));
    const release = manifest(await json(`/v1/apps/${appId}/channels/${channel}/manifest`, 16_384), profile, channel);
    const descriptor = release[role === 'first_install' ? 'first_install' : 'archive'];
    if (descriptor.size > maxArchiveBytes) fail('Archive exceeds configured capacity');
    const table = pieceDescriptor(await json(descriptor.path + '/parts', WIRE_LIMIT), descriptor, appId);
    check();
    // Exactly one archive-sized JS allocation; pieces are views into this buffer.
    const bytes = new Uint8Array(descriptor.size);
    let offset = 0;
    for (const part of table.parts) {
      check();
      const piece = bytes.subarray(offset, offset + part.size);
      await read(await request(descriptor.path + '/parts/' + part.index), piece, true);
      if (await wait(sha256(piece)) !== part.sha256) fail();
      offset += part.size;
    }
    if (offset !== bytes.byteLength || await wait(sha256(bytes)) !== descriptor.sha256) fail();
    const signature = base64Bytes(descriptor.ed25519_signature, 64);
    if (!await wait(crypto.subtle.verify('Ed25519', key, signature, bytes))) fail();
    check();
    return {bytes, manifest: release, descriptor};
  } catch (error) {
    controller.abort(error);
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
