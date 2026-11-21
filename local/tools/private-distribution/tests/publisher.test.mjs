import assert from 'node:assert/strict';
import {createHash, generateKeyPairSync, sign} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {test} from 'node:test';
import {PIECE_SIZE} from '../delivery/contract.mjs';
import {createPublisher, serializePartTable} from '../delivery/publisher.mjs';
import worker from '../delivery/worker.mjs';
import {retrieveArchive} from '../delivery/client.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const configuration = {
  app_id: 'io.example.fixture', bundle_id: 'io.example.fixture', team_id: 'EXAMPLE001',
  architecture: 'universal', minimum_macos: '15.0', data_schema_version: 1,
  origin: 'https://fixture.example',
};
const initial = {releaseId: null, generation: 0};

function scenario(t, clock = () => 1_000_000_000_000) {
  const keys = generateKeyPairSync('ed25519');
  const verificationKey = keys.publicKey.export({format: 'der', type: 'spki'}).subarray(-32).toString('base64');
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('../delivery/schema.sql', import.meta.url), 'utf8'));
  t.after(() => db.close());
  const assets = new Map();
  const faults = {provider: false, corrupt: false, holdRead: null};
  const create = product => createPublisher({
    db, configuration: product, verificationKey,
    clock,
    putPart(metadata, bytes) {
      if (faults.provider) throw new Error('Fixture upload stopped');
      if (assets.has(metadata.path)) assert.deepEqual(assets.get(metadata.path), bytes);
      assets.set(metadata.path, Buffer.from(bytes));
    },
    async readArchive({product, releaseId, kind, descriptor}) {
      if (faults.holdRead) await faults.holdRead;
      const parts = db.prepare('SELECT parts_json FROM artifact_parts WHERE app_id=? AND release_id=? AND kind=? AND artifact_sha256=?')
        .get(product.app_id, releaseId, kind, descriptor.sha256);
      const exact = Buffer.concat(JSON.parse(parts.parts_json).map(part => assets.get(part.path)));
      if (faults.corrupt) exact[0] ^= 1;
      return exact;
    },
  });
  function release(releaseId, build, version = `1.0.${build}`, product = configuration) {
    const archives = {archive: Buffer.alloc(PIECE_SIZE + 7, build), package: Buffer.from(`fixture install ${build}`)};
    function descriptor(kind) {
      const bytes = archives[kind];
      return {
        path: `/v1/apps/${product.app_id}/releases/${releaseId}/${kind}`,
        sha256: hash(bytes), size: bytes.length,
        ed25519_signature: sign(null, bytes, keys.privateKey).toString('base64'),
      };
    }
    const {origin, ...identity} = product;
    const manifest = {...identity, channel: 'qualification', qualified: false, version, build,
      qualification_id: `qual-${releaseId}`, schema: 'private-distribution/release/v1',
      source_revision: 'a'.repeat(40), archive: descriptor('archive'), first_install: descriptor('package')};
    const receipt = {release_id: releaseId, source_revision: manifest.source_revision,
      qualification_id: manifest.qualification_id, archive_sha256: manifest.archive.sha256,
      package_sha256: manifest.first_install.sha256, evidence_sha256: 'd'.repeat(64)};
    return {releaseId, manifest, archives, receipt};
  }
  return {db, assets, faults, create, release, verificationKey, publisher: create(configuration)};
}

async function stage(publisher, release) {
  return publisher.stage(release.releaseId, release.manifest, release.archives);
}

test('stage, verify and promote exact signed bytes, with idempotent retries', async t => {
  const {publisher, release, db, assets} = scenario(t);
  const first = release('first', 1);
  await stage(publisher, first);
  await stage(publisher, first);
  assert.deepEqual(publisher.pointer('stable'), initial);
  assert.deepEqual(publisher.pointer('qualification'), initial);
  assert.equal(assets.size, 3);
  assert.equal(db.prepare('SELECT count(*) AS count FROM artifact_protocols').get().count, 2);
  assert.deepEqual(await publisher.advanceQualification('first', initial), {releaseId: 'first', generation: 1});
  const stable = {releaseId: 'first', generation: 1};
  assert.deepEqual(await publisher.promote('first', initial, first.receipt), stable);
  assert.deepEqual(await publisher.promote('first', initial, first.receipt), stable);
  await assert.rejects(publisher.promote('first', stable, {...first.receipt, evidence_sha256: 'c'.repeat(64)}), /receipt already differs/);
  const stableJSON = db.prepare("SELECT manifest_json FROM releases WHERE channel='stable'").get().manifest_json;
  assert.deepEqual(JSON.parse(stableJSON), {...first.manifest, channel: 'stable', qualified: true});
});

test('rejects changed release bytes, version reuse and altered metadata with stable state intact', async t => {
  const {publisher, release, db, assets} = scenario(t);
  const first = release('first', 1);
  await stage(publisher, first);
  await publisher.advanceQualification('first', initial);
  const stable = await publisher.promote('first', initial, first.receipt);
  const before = [...assets].map(([path, bytes]) => [path, hash(bytes)]);
  await assert.rejects(stage(publisher, release('first', 2)), /Immutable release/);
  await assert.rejects(stage(publisher, release('other', 2, '1.0.1')), /Immutable release/);
  await assert.rejects(stage(publisher, release('other', 1, '1.0.9')), /Immutable release/);
  const signedMetadataChanged = {...first.manifest,
    archive: {...first.manifest.archive, ed25519_signature: Buffer.alloc(64).toString('base64')}};
  await assert.rejects(publisher.stage('first', signedMetadataChanged, first.archives), /Immutable release/);
  await assert.rejects(publisher.stage('first', first.manifest,
    {...first.archives, archive: Buffer.alloc(first.manifest.archive.size)}), /bytes or signature/);
  assert.deepEqual([...assets].map(([path, bytes]) => [path, hash(bytes)]), before);
  assert.deepEqual(publisher.pointer('stable'), stable);
  assert.equal(db.prepare('SELECT count(*) AS count FROM release_identities').get().count, 1);
});

test('interruptions and corrupt readback preserve inactive channels', async t => {
  const {publisher, release, faults, db} = scenario(t);
  const first = release('first', 1);
  faults.provider = true;
  await assert.rejects(stage(publisher, first), /upload stopped/);
  assert.equal(db.prepare('SELECT count(*) AS count FROM releases').get().count, 0);
  faults.provider = false;
  await stage(publisher, first);
  faults.corrupt = true;
  await assert.rejects(publisher.advanceQualification('first', initial), /bytes or signature/);
  faults.corrupt = false;
  await publisher.advanceQualification('first', initial);
  await assert.rejects(publisher.promote('first', initial, {...first.receipt, package_sha256: 'a'.repeat(64)}), /exact staged release/);
  faults.corrupt = true;
  await assert.rejects(publisher.promote('first', initial, first.receipt), /bytes or signature/);
  assert.deepEqual(publisher.pointer('stable'), initial);
});

test('stale and competing promotions cannot advance an already changed stable pointer', async t => {
  const {publisher, release, db} = scenario(t);
  const first = release('first', 1);
  const second = release('second', 2);
  const third = release('third', 3);
  for (const candidate of [first, second, third]) await stage(publisher, candidate);
  await publisher.advanceQualification('first', initial);
  const stable = await publisher.promote('first', initial, first.receipt);
  await publisher.advanceQualification('second', {releaseId: 'first', generation: 1});
  await assert.rejects(publisher.promote('second', initial, second.receipt), /Channel changed/);
  await publisher.advanceQualification('third', {releaseId: 'second', generation: 2});
  const competing = await Promise.allSettled([
    publisher.promote('second', stable, second.receipt),
    publisher.promote('third', stable, third.receipt),
  ]);
  assert.deepEqual(competing.map(item => item.status), ['rejected', 'fulfilled']);
  assert.deepEqual(publisher.pointer('stable'), {releaseId: 'third', generation: 2});
  assert.equal(db.prepare("SELECT count(*) AS count FROM releases WHERE channel='stable' AND release_id='second'").get().count, 0);
});

test('pause keeps a generation tombstone and recovery requires a higher build', async t => {
  const {publisher, release} = scenario(t);
  const first = release('first', 1);
  const second = release('second', 2);
  await stage(publisher, first);
  await publisher.advanceQualification('first', initial);
  const stable = await publisher.promote('first', initial, first.receipt);
  const muted = publisher.pauseStable(stable);
  assert.deepEqual(muted, {releaseId: null, generation: 2});
  await assert.rejects(publisher.promote('first', muted, first.receipt), /build must advance/);
  await stage(publisher, second);
  await publisher.advanceQualification('second', {releaseId: 'first', generation: 1});
  await assert.rejects(publisher.promote('second', initial, second.receipt), /Channel changed/);
  assert.deepEqual(await publisher.promote('second', muted, second.receipt), {releaseId: 'second', generation: 3});
});

test('grant tokens are hashed and explicit product/channel scope survives replacement and revocation', t => {
  const {publisher, db, create} = scenario(t);
  const sibling = create({...configuration, app_id: 'io.example.sibling'});
  const options = {label: 'synthetic-recipient', expiresAt: 1_000_000_060};
  assert.throws(() => publisher.createGrant('qualification', options), /scope or expiry/);
  const first = publisher.createGrant('stable', options);
  const stored = db.prepare('SELECT token_hash, revoked_at FROM grants WHERE grant_id=?').get(first.grantId);
  assert.deepEqual({...stored}, {token_hash: hash(first.access.token), revoked_at: null});
  assert.throws(() => sibling.revokeGrant(first.grantId), /Unknown grant for this product/);
  assert.throws(() => sibling.replaceGrant(first.grantId, 'stable', options), /scope differs/);
  assert.throws(() => publisher.replaceGrant(first.grantId, 'qualification', {...options, owner: true}), /scope differs/);
  const second = publisher.replaceGrant(first.grantId, 'stable', options);
  assert.notEqual(second.access.token, first.access.token);
  assert.throws(() => publisher.replaceGrant(first.grantId, 'stable', options), /already revoked or replaced/);
  publisher.revokeGrant(second.grantId);
  publisher.revokeGrant(second.grantId);
  const revoked = db.prepare('SELECT revoked_at FROM grants ORDER BY grant_id').all();
  assert.deepEqual(revoked.map(row => row.revoked_at), [1_000_000_000, 1_000_000_000]);
});

test('verified synthetic producer and recipient work together through the actual Worker', async t => {
  const {publisher, db, assets, release, verificationKey} = scenario(t, Date.now);
  const first = release('first', 1);
  await stage(publisher, first);
  const validity = Math.floor(Date.now() / 1000) + 3600;
  const owner = publisher.createGrant('qualification', {label: 'fixture-owner', owner: true, expiresAt: validity});
  const recipient = publisher.createGrant('stable', {label: 'fixture-recipient', expiresAt: validity});
  const handler = {
    RELEASE_PROFILE: JSON.stringify(configuration),
    DB: {
      withSession(mode) {
        assert.equal(mode, 'first-primary');
        return {prepare: sql => ({bind: (...args) => ({first: async () => db.prepare(sql).get(...args) ?? null})})};
      },
    },
    ASSETS: {
      async fetch(request) {
        assert.equal(request.headers.get('Authorization'), null);
        const value = assets.get(new URL(request.url).pathname);
        return value ? new Response(request.method === 'HEAD' ? null : value,
          {headers: {'Content-Length': String(value.length)}}) : new Response(null, {status: 404});
      },
    },
  };
  const options = {profile: configuration, configuredOrigin: configuration.origin,
    appId: configuration.app_id, role: 'first_install', publicKey: verificationKey,
    maxArchiveBytes: PIECE_SIZE * 2, fetch: (url, overrides) => worker.fetch(new Request(url, overrides), handler)};
  await assert.rejects(retrieveArchive({...options, channel: 'stable', accessFile: recipient.access}), /request failed/);
  await publisher.advanceQualification('first', initial);
  const qualified = await retrieveArchive({...options, channel: 'qualification', accessFile: owner.access});
  assert.deepEqual(Buffer.from(qualified.bytes), first.archives.package);
  const stable = await publisher.promote('first', initial, first.receipt);
  const installed = await retrieveArchive({...options, channel: 'stable', accessFile: recipient.access});
  assert.deepEqual(Buffer.from(installed.bytes), first.archives.package);
  const update = await retrieveArchive({...options, role: 'update', channel: 'stable', accessFile: recipient.access});
  assert.deepEqual(Buffer.from(update.bytes), first.archives.archive);
  publisher.pauseStable(stable);
  await assert.rejects(retrieveArchive({...options, channel: 'stable', accessFile: recipient.access}), /request failed/);
  publisher.revokeGrant(owner.grantId);
  await assert.rejects(retrieveArchive({...options, channel: 'qualification', accessFile: owner.access}), /request failed/);
});

test('publication rejects part metadata that exceeds the Worker read capacity', () => {
  const app = 'a'.repeat(128), releaseId = 'r'.repeat(128), digest = 'd'.repeat(64);
  const metadata = Array.from({length: 2048}, (_, index) => ({
    index, path: `/_private/${app}/${releaseId}/package/${digest}/${index}-${digest}.part`,
    sha256: digest, size: PIECE_SIZE,
  }));
  assert.throws(() => serializePartTable(metadata), /Worker metadata limit/);
  assert.equal(JSON.parse(serializePartTable(metadata.slice(0, 2))).length, 2);
});
