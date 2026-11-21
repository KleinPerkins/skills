// Adapted from KleinPerkins/machine-monitor 4f26c15527ef6912434e3953de6169aed8244e28,
// delivery/worker.mjs, under the source owner's explicit adaptation authorization.
import {TOKEN, ID, profile, manifest, sha256, parts, PIECE_SIZE, MAX_PIECES, INTERNAL_LIMIT, WIRE_LIMIT, parseWireJSON} from './contract.mjs';
const POLICY = {
  'Cache-Control':'private, no-store, max-age=0', 'CDN-Cache-Control':'no-store',
  'Cloudflare-CDN-Cache-Control':'no-store', 'Pragma':'no-cache',
  'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer',
  'Cross-Origin-Resource-Policy':'same-origin', 'Vary':'Authorization, Origin',
  'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security':'max-age=31536000',
};
const BINARY_HEADERS = new Headers({...POLICY,'Content-Type':'application/octet-stream','Accept-Ranges':'none'});
const reply = (value, status=200, headers={}) => {
  const raw=JSON.stringify(value);
  if(new TextEncoder().encode(raw).byteLength>WIRE_LIMIT)throw new Error('wire limit');
  return new Response(raw, {status, headers:{...POLICY,'Content-Type':'application/json',...headers}});
};
const deny = () => reply({error:'access_denied'},401);
// Share a four-entry/1 MiB budget for exact immutable metadata validation.
// Authorization and asset bodies are never cached; row bindings are checked on every request.
const checkedParts = new Map();
let checkedPartsBytes = 0;
function rememberMetadata(raw, rawSize, entry) {
  const prior = checkedParts.get(raw);
  if (prior) { checkedParts.delete(raw); checkedPartsBytes -= prior.rawSize; }
  while (checkedParts.size >= 4 || checkedPartsBytes + rawSize > INTERNAL_LIMIT) {
    const first = checkedParts.keys().next().value;
    checkedPartsBytes -= checkedParts.get(first).rawSize; checkedParts.delete(first);
  }
  checkedParts.set(raw, Object.freeze({...entry, rawSize})); checkedPartsBytes += rawSize;
}
function canonicalManifest(raw, p, channel, release) {
  const app=p.app_id, profileKey=JSON.stringify(p);
  const hit = checkedParts.get(raw);
  if (hit?.entryType === 'manifest' && hit.profileKey === profileKey && hit.app === app && hit.channel === channel && hit.release === release) return hit.value;
  const value = manifest(parseWireJSON(raw), p, channel, release);
  const pending = [value];
  while (pending.length) {
    const item = pending.pop();
    if (item && typeof item === 'object' && !Object.isFrozen(item)) {
      for (const child of Object.values(item)) if (child && typeof child === 'object') pending.push(child);
      Object.freeze(item);
    }
  }
  rememberMetadata(raw, new TextEncoder().encode(raw).byteLength, {entryType:'manifest', profileKey, app, channel, release, value});
  return value;
}
function canonicalParts(raw, app, release, kind, descriptor) {
  const hit = checkedParts.get(raw);
  if (hit?.entryType === 'parts' && hit.app === app && hit.release === release && hit.kind === kind &&
      hit.sha256 === descriptor.sha256 && hit.size === descriptor.size) return hit.value;
  // Exact compact serialization equality rejects duplicate keys, escaped aliases,
  // whitespace and alternate numeric spellings without a second token walk over
  // the maximum 2048-row table. Validation is cached only for these exact bytes.
  const ordered = parts(JSON.parse(raw), app, release, kind, descriptor);
  if (JSON.stringify(ordered) !== raw) throw new Error('parts');
  for (const part of ordered) Object.freeze(part);
  Object.freeze(ordered);
  const value=Object.freeze({ordered,bounded:ordered.length===Math.ceil(descriptor.size/PIECE_SIZE)&&
    !ordered.some((p,i)=>p.size>PIECE_SIZE||(i<ordered.length-1&&p.size!==PIECE_SIZE))});
  rememberMetadata(raw, raw.length, {entryType:'parts',app,release,kind,sha256:descriptor.sha256,size:descriptor.size,value});
  return value;
}
const READ_MS=30000;
// Cleanup is best effort. The body producer cannot extend the request's bound
// by delaying the promise returned from cancel().
function cancelBody(body) {
  if (body) void body.cancel().catch(()=>{});
}

function releaseReader(reader) {
  cancelBody(reader);
  reader.releaseLock();
}

async function timed(operation, cancel=()=>{}, signal) {
  let timer, abort;
  try {
    return await Promise.race([operation,new Promise((_,reject)=>{
      const stop=reason=>{reject(new Error(reason));cancel();};
      timer=setTimeout(()=>stop('timeout'),READ_MS);
      if(signal){
        abort=()=>stop('cancelled');
        signal.addEventListener('abort',abort,{once:true});
        if(signal.aborted)abort();
      }
    })]);
  } finally {
    clearTimeout(timer);
    if(abort)signal.removeEventListener('abort',abort);
  }
}
async function asset(env, approved, part, method, signal) {
  // Construct a fresh internal request: never forward bearer/override/cookie headers.
  const abort=new AbortController();
  const cancel=()=>abort.abort();
  if(signal?.aborted)throw new Error('cancelled');
  const pending=env.ASSETS.fetch(new Request(approved+part.path,{method,signal:abort.signal}));
  Promise.resolve(pending).then(response=>{
    if(abort.signal.aborted)cancelBody(response.body);
  },()=>{});
  const response=await timed(pending,cancel,signal);
  // Static Assets may omit Content-Length. Reject an inconsistent declaration;
  // pieceBytes() enforces the immutable size and EOF before emitting bytes.
  const length=response.headers.get('Content-Length');
  if(response.status!==200 || (length!==null && length!==String(part.size)) || response.headers.get('Content-Encoding')) {
    cancelBody(response.body);
    throw new Error('asset');
  }
  return response;
}
async function pieceBytes(response,part,signal) {
  if(!response.body||part.size>PIECE_SIZE)throw new Error('asset');
  let reader,native=false;
  try{reader=response.body.getReader({mode:'byob'});native=typeof reader.readAtLeast==='function';if(!native){reader.releaseLock();reader=null;}}catch{}
  reader??=response.body.getReader();
  let bytes=new Uint8Array(part.size+1),count=0,cancelled=false;
  const cancel=()=>{cancelled=true;reader.cancel().catch(()=>{});};
  try {
    if(signal?.aborted)throw new Error('cancelled');
    return await timed((async()=>{
      while(true){
        if(cancelled||signal?.aborted)throw new Error('cancelled');
        const view=count?new Uint8Array(1):bytes;
        const item=await(native?reader.readAtLeast(view.length,view):reader.read());
        if(cancelled||signal?.aborted)throw new Error('cancelled');
        if(item.value?.byteLength){
          if(count+item.value.byteLength>part.size)throw new Error('length');
          // Native BYOB may transfer the supplied buffer. Retain its returned
          // storage rather than writing to a detached original view.
          if(native&&count===0)bytes=new Uint8Array(item.value.buffer,item.value.byteOffset,item.value.byteLength);
          else bytes.set(item.value,count);
          count+=item.value.byteLength;
        }else if(!item.done)throw new Error('length');
        // readAtLeast returns fewer than the requested minimum only at EOF.
        // The size+1 probe therefore proves EOF without a redundant second read.
        if(native || item.done)break;
      }
      if(cancelled||signal?.aborted||count!==part.size)throw new Error('length');
      return bytes.subarray(0,count);
    })(),cancel,signal);
  } finally {
    releaseReader(reader);
  }
}
const auth = `FROM grants g JOIN entitlements e ON e.grant_id=g.grant_id
 WHERE g.token_hash=? AND e.app_id=? AND e.channel=? AND g.revoked_at IS NULL
 AND typeof(g.expires_at)='integer' AND g.expires_at>? AND typeof(g.is_owner)='integer' AND g.is_owner IN (0,1) AND (e.channel!='qualification' OR g.is_owner=1)`;
// Exactly one primary read joins authorization and the release: a session's later
// reads may route to replicas, so do not reuse a session for the next request.
async function primary(env, sql, values) {
  return timed(env.DB.withSession('first-primary').prepare(sql).bind(...values).first());
}
async function smallJSON(request) {
  if (request.headers.get('Content-Type')?.split(';')[0].trim() !== 'application/json') throw new Error('body');
  const reader=request.body?.getReader(); if (!reader) throw new Error('body');
  let size=0, chunks=[];
  try { await timed((async()=>{while (true) {const {done,value}=await reader.read(); if(done)break; size+=value.length;if(size>1024)throw new Error('body');chunks.push(value);}})(),()=>cancelBody(reader),request.signal);}
  finally {releaseReader(reader);}
  const bytes=new Uint8Array(size);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
  return parseWireJSON(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
}
export default {async fetch(request, env, ctx) {
  try {
    if(typeof env.RELEASE_PROFILE!=='string'||new TextEncoder().encode(env.RELEASE_PROFILE).byteLength>4096)throw new Error('profile');
    const p=profile(parseWireJSON(env.RELEASE_PROFILE)), APP=p.app_id, approved=p.origin, url=new URL(request.url);
    if(url.origin!==approved || url.search || url.hash || url.username || url.password) return reply({error:'invalid_request'},400);
    if(request.headers.has('Cloudflare-Workers-Version-Overrides'))return reply({error:'version_override_denied'},403);
    const requestedOrigin=request.headers.get('Origin');
    if((requestedOrigin && requestedOrigin!==approved) || request.headers.get('Sec-Fetch-Site')==='cross-site') return reply({error:'cross_origin_denied'},403);
    const accessRoute=url.pathname==='/v1/access/check';
    const m=url.pathname.match(/^\/v1\/apps\/([A-Za-z0-9._-]+)\/channels\/(stable|qualification)\/manifest$/);
    const a=url.pathname.match(/^\/v1\/apps\/([A-Za-z0-9._-]+)\/releases\/([A-Za-z0-9._-]+)\/(archive|package)(?:\/(parts)(?:\/(0|[1-9][0-9]{0,3}))?)?$/);
    if(!accessRoute&&!m&&!a) return reply({error:'not_found'},404);
    if((accessRoute&&request.method!=='POST')||(m&&request.method!=='GET')||(a&&(!['GET','HEAD'].includes(request.method)||(a[4]&&a[5]===undefined&&request.method!=='GET'))))return reply({error:'method_not_allowed'},405);
    const match=request.headers.get('Authorization')?.match(/^Bearer ([A-Za-z0-9_-]{43})$/);
    if(!match || !TOKEN.test(match[1]) || !'AEIMQUYcgkosw048'.includes(match[1].at(-1)))return deny();
    const hash=await sha256(new TextEncoder().encode(match[1])),now=Math.floor(Date.now()/1000);
    if(accessRoute){
      let body;try{body=await smallJSON(request);}catch{return reply({error:'invalid_request'},400);}
      if(!body || typeof body!=='object' || Array.isArray(body) || body.app_id!==APP || !['stable','qualification'].includes(body.channel) || Object.keys(body).sort().join(',')!=='app_id,channel')return deny();
      const row=await primary(env,`SELECT g.grant_id,g.expires_at ${auth}`,[hash,body.app_id,body.channel,now]);
      if(row && (typeof row.grant_id!=='string'||!ID.test(row.grant_id)||!Number.isSafeInteger(row.expires_at)||row.expires_at<=now))throw new Error('grant');
      return row?reply({schema:'private-distribution/access-status/v1',app_id:body.app_id,channel:body.channel,grant_id:row.grant_id,expires_at:row.expires_at}):deny();
    }
    if((m||a)[1]!==APP)return deny();
    let row;
    if(m){
      row=await primary(env,`SELECT r.release_id,r.channel,r.manifest_json,r.archive_sha256,r.archive_size,r.object_key FROM channels c JOIN releases r USING(app_id,release_id,channel)
        WHERE c.app_id=? AND c.channel=? AND EXISTS(SELECT 1 ${auth})`,[m[1],m[2],hash,m[1],m[2],now]);
    }else{
      if(!ID.test(a[2]))return deny();
      row=await primary(env,`SELECT r.release_id,r.channel,r.manifest_json,r.archive_sha256,r.archive_size,r.object_key,p.parts_json,t.descriptor_schema,t.part_size FROM releases r LEFT JOIN artifact_parts p
        ON p.app_id=r.app_id AND p.release_id=r.release_id AND p.kind='${a[3]}'
        AND p.artifact_sha256=json_extract(r.manifest_json,'$.${a[3]==='package'?'first_install':'archive'}.sha256')
        LEFT JOIN artifact_protocols t ON t.app_id=p.app_id AND t.release_id=p.release_id
        AND t.kind=p.kind AND t.artifact_sha256=p.artifact_sha256
        WHERE r.app_id=? AND r.release_id=?
        AND (r.channel!='stable' OR EXISTS(SELECT 1 FROM channels active WHERE active.app_id=r.app_id AND active.channel='stable' AND active.release_id IS NOT NULL))
        AND EXISTS(SELECT 1 FROM grants g JOIN entitlements e ON e.grant_id=g.grant_id
          WHERE g.token_hash=? AND e.app_id=r.app_id AND e.channel=r.channel AND g.revoked_at IS NULL
          AND typeof(g.expires_at)='integer' AND g.expires_at>? AND typeof(g.is_owner)='integer' AND g.is_owner IN (0,1) AND (r.channel!='qualification' OR g.is_owner=1))
        ORDER BY CASE r.channel WHEN 'stable' THEN 0 ELSE 1 END LIMIT 1`,[a[1],a[2],hash,now]);
    }
    if(!row)return deny();
    if(typeof row.release_id!=='string'||!ID.test(row.release_id)||(a&&row.release_id!==a[2])||typeof row.manifest_json!=='string'||new TextEncoder().encode(row.manifest_json).byteLength>16384)throw new Error('manifest');
    const release=canonicalManifest(row.manifest_json,p,m?.[2],row.release_id);
    if(release.channel!==row.channel || release.archive.sha256!==row.archive_sha256 || release.archive.size!==row.archive_size ||
       row.object_key!==`${APP}/${release.archive.sha256}.zip`)throw new Error('manifest');
    if(m)return reply(release);
    const artifact=a[3]==='package'?release.first_install:release.archive;
    if(row.descriptor_schema!=='private-distribution/artifact-parts/v2'||row.part_size!==PIECE_SIZE)throw new Error('legacy transport');
    if(typeof row.parts_json!=='string'||new TextEncoder().encode(row.parts_json).byteLength>INTERNAL_LIMIT)throw new Error('parts');
    const {ordered,bounded}=canonicalParts(row.parts_json,APP,row.release_id,a[3],artifact);
    // Conditional/range requests authorize first; never return a cached 304.
    if(request.headers.has('Range'))return reply({error:'ranges_unsupported'},416,{'Accept-Ranges':'none'});
    if([...request.headers.keys()].some(k=>k.startsWith('if-')))return reply({error:'conditions_unsupported'},400);
    // Legacy aggregate locators are identities only; old owner-only builds must
    // not retain an unqualified expensive concatenation path.
    if(!a[4])throw new Error('aggregate unavailable');
    // Retention also understands legacy20MiB and1MiB rows; every current route,
    // including HEAD, requires the bounded256KiB layout before reading any asset.
    if(!bounded)throw new Error('pieces');
    // Input metadata and bounded layout are already fully validated above.
    // Project only the three public fields; revalidating this new object repeats
    // the same per-piece work on every descriptor request.
    if(a[5]===undefined)return reply({schema:'private-distribution/artifact-parts/v2',app_id:APP,release_id:a[2],kind:a[3],
      artifact_sha256:artifact.sha256,artifact_size:artifact.size,part_size:PIECE_SIZE,
      parts:ordered.map(({index,size,sha256})=>({index,size,sha256}))});
    if(Number(a[5])>=MAX_PIECES)return reply({error:'invalid_piece'},400);
    const part=ordered[Number(a[5])];
    if(!part)return reply({error:'invalid_piece'},400);
    const response=await asset(env,approved,part,request.method,request.signal);
    let body=null;
    if(request.method!=='HEAD') {
      const bytes=await pieceBytes(response,part,request.signal);
      // EOF and size are validated before any bytes escape. Workers knows the
      // fixed byte view's length without an additional stream pipeline.
      if(await sha256(bytes)!==part.sha256)throw new Error('integrity');
      body=bytes;
    }
    const headers=new Headers(BINARY_HEADERS);
    headers.set('Content-Length',String(part.size));
    return new Response(body,{headers});
  } catch {return reply({error:'service_unavailable'},503,{'Retry-After':'30'});}
}};
