// Publication state machine adapted from the pinned Machine Monitor publisher.
// Provider bindings and all live approval decisions belong to the caller.
import {createHash, createPublicKey, randomBytes, randomUUID, verify} from 'node:crypto';
import {INTERNAL_LIMIT, manifest, profile, PIECE_SIZE} from './contract.mjs';

const PROTOCOL = 'private-distribution/artifact-parts/v2';
const HASH = /^[0-9a-f]{64}$/;
const GRANT = /^[0-9a-f-]{36}$/;
const ID = /^[A-Za-z0-9_-]{1,128}$/;
const KINDS = [['archive', 'archive'], ['package', 'first_install']];
const CHANNELS = ['stable', 'qualification'];

const digest = bytes => createHash('sha256').update(bytes).digest('hex');

function compact(value) {
  if (Array.isArray(value)) return '[' + value.map(compact).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + compact(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function publicKey(encoded) {
  if (typeof encoded !== 'string' || !/^[A-Za-z0-9+/]{43}=$/.test(encoded)) {
    throw new Error('Invalid Ed25519 public key');
  }
  const bytes = Buffer.from(encoded, 'base64');
  if (bytes.length !== 32 || bytes.toString('base64') !== encoded) throw new Error('Invalid Ed25519 public key');
  const prefix = Buffer.from('302a300506032b6570032100', 'hex');
  return createPublicKey({key: Buffer.concat([prefix, bytes]), format: 'der', type: 'spki'});
}

function requireArtifact(bytes, expected, key) {
  if (!(bytes instanceof Uint8Array) || bytes.byteLength !== expected.size ||
      digest(bytes) !== expected.sha256 ||
      !verify(null, bytes, key, Buffer.from(expected.ed25519_signature, 'base64'))) {
    throw new Error('Archive bytes or signature differ from the release manifest');
  }
}

export function serializePartTable(metadata) {
  const json = compact(metadata);
  if (Buffer.byteLength(json) > INTERNAL_LIMIT) throw new Error('Part table exceeds the Worker metadata limit');
  return json;
}

function splitArtifact(bytes, app, release, kind, hash) {
  const pieces = [];
  for (let offset = 0; offset < bytes.length; offset += PIECE_SIZE) {
    const part = bytes.subarray(offset, offset + PIECE_SIZE);
    const sha = digest(part);
    const index = pieces.length;
    pieces.push({
      metadata: {index, path: `/_private/${app}/${release}/${kind}/${hash}/${index}-${sha}.part`,
        sha256: sha, size: part.byteLength},
      bytes: part,
    });
  }
  return pieces;
}

function inTransaction(db, work) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const result = work();
    db.exec('COMMIT');
    return result;
  } catch (error) {
    db.exec('ROLLBACK');
    throw error;
  }
}

// This port provides deterministic local proof of the SQLite transaction
// contract. A provider connector must separately qualify atomic D1 execution.
export function createPublisher({db, configuration, verificationKey, putPart, readArchive, clock = Date.now}) {
  const product = Object.freeze({...profile(configuration)});
  const key = publicKey(verificationKey);
  if (typeof putPart !== 'function' || typeof readArchive !== 'function') throw new Error('Missing artifact port');
  const app = product.app_id;
  const execute = (sql, ...args) => db.prepare(sql).run(...args);
  const row = (sql, ...args) => db.prepare(sql).get(...args);
  const epoch = () => Math.floor(clock() / 1000);

  function pointer(channel) {
    if (!CHANNELS.includes(channel)) throw new Error('Unknown release channel');
    const found = row('SELECT release_id, generation FROM channels WHERE app_id=? AND channel=?', app, channel);
    return found ? {releaseId: found.release_id, generation: found.generation} : {releaseId: null, generation: 0};
  }

  function requireExpected(current, expected) {
    if (expected?.generation !== current.generation || expected?.releaseId !== current.releaseId) {
      throw new Error('Channel changed since the expected observation');
    }
  }

  function setPointer(channel, current, releaseId) {
    if (current.generation === 0) {
      execute('INSERT INTO channels(app_id,channel,release_id,generation) VALUES(?,?,?,1)', app, channel, releaseId);
    } else {
      const result = execute(`UPDATE channels SET release_id=?,generation=generation+1
        WHERE app_id=? AND channel=? AND generation=? AND release_id IS ?`,
        releaseId, app, channel, current.generation, current.releaseId);
      if (result.changes !== 1) throw new Error('Concurrent channel transition');
    }
    return pointer(channel);
  }

  function insertRelease(releaseId, value, evidence) {
    execute(`INSERT INTO releases(app_id,release_id,channel,manifest_json,archive_sha256,archive_size,object_key,qualification_id,evidence_json)
      VALUES(?,?,?,?,?,?,?,?,?)`, app, releaseId, value.channel, compact(value),
      value.archive.sha256, value.archive.size, `${app}/${value.archive.sha256}.zip`,
      value.qualification_id, compact(evidence));
  }

  function qualification(releaseId) {
    if (typeof releaseId !== 'string' || !ID.test(releaseId)) throw new Error('Invalid release identity');
    const found = row("SELECT manifest_json FROM releases WHERE app_id=? AND release_id=? AND channel='qualification'",
      app, releaseId);
    if (!found) throw new Error('Unknown qualification release');
    return manifest(JSON.parse(found.manifest_json), product, 'qualification', releaseId);
  }

  async function readback(value, releaseId) {
    for (const [kind, field] of KINDS) {
      const exact = await readArchive({product, releaseId, kind, descriptor: value[field]});
      requireArtifact(exact, value[field], key);
    }
  }

  async function stage(releaseId, value, archives) {
    if (typeof releaseId !== 'string' || !ID.test(releaseId)) throw new Error('Invalid release identity');
    const manifestJSON = compact(manifest(value, product, 'qualification', releaseId));
    if (Buffer.byteLength(manifestJSON) > 16_384) throw new Error('Release manifest exceeds its wire limit');
    const candidate = JSON.parse(manifestJSON);
    if (candidate.qualified !== false) throw new Error('Stage requires an unqualified manifest');
    const previous = row(`SELECT release_id,manifest_json FROM release_identities
      WHERE app_id=? AND (release_id=? OR version=? OR build=?)
      ORDER BY CASE WHEN release_id=? THEN 0 ELSE 1 END LIMIT 1`,
      app, releaseId, candidate.version, candidate.build, releaseId);
    if (previous && (previous.release_id !== releaseId || previous.manifest_json !== manifestJSON)) {
      throw new Error('Immutable release, version or build identity already differs');
    }

    const assets = KINDS.map(([kind, field]) => {
      // Own bytes across asynchronous callbacks. A caller cannot mutate staged
      // input while storage is in flight.
      const source = archives?.[kind];
      if (!(source instanceof Uint8Array) || source.byteLength !== candidate[field].size) {
        throw new Error('Archive length differs from the release manifest');
      }
      const bytes = Buffer.from(source);
      requireArtifact(bytes, candidate[field], key);
      const hash = candidate[field].sha256;
      const parts = splitArtifact(bytes, app, releaseId, kind, hash);
      return {kind, hash, parts, metadata: serializePartTable(parts.map(part => part.metadata))};
    });
    if (previous) {
      await readback(candidate, releaseId);
      return releaseId;
    }
    // A racing refusal can leave content-addressed orphan pieces. They have
    // no public route and cannot overwrite a committed artifact.
    for (const {parts} of assets) {
      for (const {metadata, bytes} of parts) await putPart(metadata, bytes);
    }
    return inTransaction(db, () => {
      execute(`INSERT INTO release_identities(app_id,release_id,version,build,manifest_json)
        VALUES(?,?,?,?,?) ON CONFLICT(app_id,release_id) DO NOTHING`,
        app, releaseId, candidate.version, candidate.build, manifestJSON);
      const reserved = row('SELECT manifest_json FROM release_identities WHERE app_id=? AND release_id=?', app, releaseId);
      if (reserved.manifest_json !== manifestJSON) throw new Error('Immutable release identity already differs');
      const already = row("SELECT 1 FROM releases WHERE app_id=? AND release_id=? AND channel='qualification'", app, releaseId);
      if (already) return releaseId;
      for (const {kind, hash, metadata} of assets) {
        execute('INSERT INTO artifact_parts VALUES(?,?,?,?,?)', app, releaseId, kind, hash, metadata);
        execute('INSERT INTO artifact_protocols VALUES(?,?,?,?,?,?)', app, releaseId, kind, hash, PROTOCOL, PIECE_SIZE);
      }
      insertRelease(releaseId, candidate, {});
      return releaseId;
    });
  }

  async function advanceQualification(releaseId, expected) {
    const candidate = qualification(releaseId);
    await readback(candidate, releaseId);
    return inTransaction(db, () => {
      const current = pointer('qualification');
      if (current.releaseId === releaseId) return current;
      requireExpected(current, expected);
      if (current.releaseId && qualification(current.releaseId).build >= candidate.build) {
        throw new Error('Qualification build must advance');
      }
      return setPointer('qualification', current, releaseId);
    });
  }

  async function promote(releaseId, expected, receipt) {
    const candidate = qualification(releaseId);
    const evidence = {
      release_id: releaseId, source_revision: candidate.source_revision,
      archive_sha256: candidate.archive.sha256, package_sha256: candidate.first_install.sha256,
      qualification_id: candidate.qualification_id,
    };
    if (!receipt || !HASH.test(receipt.evidence_sha256 ?? '') ||
        compact(receipt) !== compact({...evidence, evidence_sha256: receipt.evidence_sha256})) {
      throw new Error('Qualification receipt does not cover the exact staged release');
    }
    const evidenceJSON = compact(receipt);
    await readback(candidate, releaseId);
    const stable = {...candidate, channel: 'stable', qualified: true};
    return inTransaction(db, () => {
      const current = pointer('stable');
      if (current.releaseId === releaseId) {
        const published = row("SELECT evidence_json FROM releases WHERE app_id=? AND release_id=? AND channel='stable'", app, releaseId);
        if (published?.evidence_json !== evidenceJSON) throw new Error('Stable promotion receipt already differs');
        return current;
      }
      requireExpected(current, expected);
      if (pointer('qualification').releaseId !== releaseId) throw new Error('Qualification pointer no longer matches');
      const highest = row(`SELECT max(i.build) AS build FROM release_identities i JOIN releases r USING(app_id,release_id)
        WHERE r.app_id=? AND r.channel='stable'`, app);
      if (highest.build !== null && candidate.build <= highest.build) throw new Error('Stable build must advance');
      insertRelease(releaseId, stable, JSON.parse(evidenceJSON));
      return setPointer('stable', current, releaseId);
    });
  }

  function pauseStable(expected) {
    return inTransaction(db, () => {
      const current = pointer('stable');
      requireExpected(current, expected);
      return current.releaseId === null ? current : setPointer('stable', current, null);
    });
  }

  function insertGrant(channel, options, replacedId) {
    const {label, expiresAt, owner = false} = options;
    const now = epoch();
    if (!CHANNELS.includes(channel) || typeof label !== 'string' || !ID.test(label) ||
        typeof owner !== 'boolean' || (channel === 'qualification' && !owner) ||
        !Number.isSafeInteger(expiresAt) || expiresAt <= now) throw new Error('Invalid grant scope or expiry');
    const token = randomBytes(32).toString('base64url');
    const grantId = randomUUID();
    return inTransaction(db, () => {
      if (replacedId !== undefined) {
        const previous = row(`SELECT g.is_owner FROM grants g JOIN entitlements e USING(grant_id)
          WHERE g.grant_id=? AND e.app_id=? AND e.channel=?`, replacedId, app, channel);
        if (!previous || previous.is_owner !== Number(owner)) throw new Error('Replacement grant scope differs');
        const revoked = execute('UPDATE grants SET revoked_at=? WHERE grant_id=? AND revoked_at IS NULL', now, replacedId);
        if (revoked.changes !== 1) throw new Error('Grant was already revoked or replaced');
      }
      execute('INSERT INTO grants(grant_id,token_hash,label,is_owner,expires_at,created_at) VALUES(?,?,?,?,?,?)',
        grantId, digest(token), label, Number(owner), expiresAt, now);
      execute('INSERT INTO entitlements(grant_id,app_id,channel) VALUES(?,?,?)', grantId, app, channel);
      return {grantId, access: {schema: 'private-distribution/access/v1', app_id: app, origin: product.origin, token}};
    });
  }

  function revokeGrant(grantId) {
    if (typeof grantId !== 'string' || !GRANT.test(grantId)) throw new Error('Invalid grant identity');
    const result = execute(`UPDATE grants SET revoked_at=coalesce(revoked_at,?)
      WHERE grant_id=? AND EXISTS (SELECT 1 FROM entitlements WHERE grant_id=? AND app_id=?)`,
      epoch(), grantId, grantId, app);
    if (result.changes !== 1) throw new Error('Unknown grant for this product');
  }

  return {
    pointer, stage, advanceQualification, promote, pauseStable, revokeGrant,
    createGrant: (channel, options) => insertGrant(channel, options),
    replaceGrant: (grantId, channel, options) => {
      if (typeof grantId !== 'string' || !GRANT.test(grantId)) throw new Error('Invalid grant identity');
      return insertGrant(channel, options, grantId);
    },
  };
}
