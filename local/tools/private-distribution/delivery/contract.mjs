// Adapted from KleinPerkins/machine-monitor 4f26c15527ef6912434e3953de6169aed8244e28,
// delivery/contract.mjs, under the source owner's explicit adaptation authorization.
// Import-safe wire validation. Every identity comes from a closed nonsecret profile.
const APP_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const VERSION = /^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,3}$/;
const fields = value => value && typeof value === 'object' && !Array.isArray(value) ? Object.keys(value).sort().join(',') : '';
export function profile(value) {
  if (fields(value) !== 'app_id,architecture,bundle_id,data_schema_version,minimum_macos,origin,team_id' ||
      typeof value.app_id !== 'string' || !APP_ID.test(value.app_id) ||
      typeof value.bundle_id !== 'string' || !APP_ID.test(value.bundle_id) ||
      typeof value.team_id !== 'string' || !/^[A-Z0-9]{10}$/.test(value.team_id) ||
      !['arm64','x86_64','universal'].includes(value.architecture) ||
      typeof value.minimum_macos !== 'string' || !VERSION.test(value.minimum_macos) ||
      !Number.isSafeInteger(value.data_schema_version) || value.data_schema_version < 1) throw new Error('invalid profile');
  origin(value.origin);
  return value;
}
export const MAX_ARCHIVE = 512 * 1024 * 1024;
export const TOKEN = /^[A-Za-z0-9_-]{43}$/;
export const ID = /^[A-Za-z0-9_-]{1,128}$/;
export function origin(value) {
  if (typeof value !== 'string') throw new Error('invalid origin');
  const u = new URL(value);
  if (u.protocol !== 'https:' || u.username || u.password || u.origin !== value || u.hostname.endsWith('.r2.dev')) throw new Error('invalid origin');
  return value;
}
export function access(value, expectedProfile) {
  const p=profile(expectedProfile);
  if (!value || fields(value) !== 'app_id,origin,schema,token' ||
      value.schema !== 'private-distribution/access/v1' || value.app_id !== p.app_id ||
      origin(value.origin) !== p.origin || typeof value.token !== 'string' || !TOKEN.test(value.token) ||
      // Canonical base64url: the last character encodes only four significant bits.
      !'AEIMQUYcgkosw048'.includes(value.token.at(-1))) throw new Error('invalid access file');
  return value;
}
export function manifest(value, expectedProfile, channel, release) {
  const p=profile(expectedProfile), app=p.app_id;
  const fields='app_id,architecture,archive,build,bundle_id,channel,data_schema_version,first_install,minimum_macos,qualification_id,qualified,schema,source_revision,team_id,version';
  if (!value || typeof value !== 'object' || Object.keys(value).sort().join(',')!==fields || value.schema !== 'private-distribution/release/v1' ||
      value.app_id !== app || value.bundle_id !== p.bundle_id || value.team_id !== p.team_id ||
      !['stable', 'qualification'].includes(value.channel) || (channel && value.channel !== channel) ||
      typeof value.version !== 'string' || !/^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,3}$/.test(value.version) ||
      !Number.isSafeInteger(value.build) || value.build < 1 || value.minimum_macos !== p.minimum_macos ||
      value.architecture !== p.architecture || value.data_schema_version !== p.data_schema_version ||
      typeof value.source_revision !== 'string' || !/^[a-f0-9]{40}$/.test(value.source_revision) || typeof value.qualification_id !== 'string' || !ID.test(value.qualification_id) ||
      typeof value.qualified !== 'boolean' || (value.channel === 'stable' && value.qualified !== true)) throw new Error('invalid manifest');
  validateDescriptor(value.archive, app, release, 'archive');
  validateDescriptor(value.first_install, app, release, 'package');
  if (value.archive.path.split('/').at(-2) !== value.first_install.path.split('/').at(-2)) throw new Error('release mismatch');
  return value;
}
export function validateDescriptor(a, app, release, kind) {
  if (typeof app !== 'string' || !APP_ID.test(app) || !['archive','package'].includes(kind) || (release !== undefined && (typeof release !== 'string' || !ID.test(release)))) throw new Error('invalid descriptor binding');
  const prefix = `/v1/apps/${app}/releases/`;
  if (!a || Object.keys(a).sort().join(',')!=='ed25519_signature,path,sha256,size' || typeof a.path !== 'string' || !a.path.startsWith(prefix) || !a.path.endsWith('/'+kind) ||
      !ID.test(a.path.slice(prefix.length, -(kind.length+1))) || (release && a.path !== `${prefix}${release}/${kind}`) ||
      !Number.isSafeInteger(a.size) || a.size < 1 || a.size > MAX_ARCHIVE || (typeof a.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(a.sha256)) ||
      typeof a.ed25519_signature !== 'string' || !/^[A-Za-z0-9+/]{86}==$/.test(a.ed25519_signature) ||
      !'AQgw'.includes(a.ed25519_signature.at(-3))) throw new Error('invalid archive');
}
export async function sha256(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), x => x.toString(16).padStart(2,'0')).join('');
}

// Immutable publication-only metadata. Full archive hashes/signatures stay on wire.
export const PART_SIZE=20*1024*1024;
export const PIECE_SIZE=256*1024;
export const MAX_PIECES=2048;
export const WIRE_LIMIT=256*1024;
export const INTERNAL_LIMIT=1024*1024;
export function parts(value,app,release,kind,descriptor) {
  if(!Array.isArray(value)||value.length<1||value.length>MAX_PIECES)throw new Error('parts');
  const stride=value[0]?.size;
  if(value.length>1&&![PART_SIZE,1024*1024,PIECE_SIZE].includes(stride))throw new Error('parts');
  let total=0;
  value.forEach((part,index)=>{
    if(!part || Object.keys(part).sort().join(',')!=='index,path,sha256,size' || part.index!==index ||
      !Number.isSafeInteger(part.size)||part.size<1||part.size>PART_SIZE ||
      (index<value.length-1&&part.size!==stride) || part.size>stride || typeof part.sha256!=='string' || !/^[a-f0-9]{64}$/.test(part.sha256) ||
      part.path!==`/_private/${app}/${release}/${kind}/${descriptor.sha256}/${index}-${part.sha256}.part`)throw new Error('parts');
    total+=part.size;
  });
  if(total!==descriptor.size)throw new Error('parts');
  return value;
}

export function pieceDescriptor(value,descriptor,app_id) {
  const kind=descriptor.path.split('/').at(-1),release=descriptor.path.split('/').at(-2);
  validateDescriptor(descriptor,app_id,release,kind);
  if(!['archive','package'].includes(kind)||!value||Object.keys(value).sort().join(',')!=='app_id,artifact_sha256,artifact_size,kind,part_size,parts,release_id,schema'||
     value.schema!=='private-distribution/artifact-parts/v2'||value.app_id!==app_id||value.release_id!==release||value.kind!==kind||
     value.artifact_sha256!==descriptor.sha256||value.artifact_size!==descriptor.size||value.part_size!==PIECE_SIZE||
     !Array.isArray(value.parts)||value.parts.length!==Math.ceil(descriptor.size/PIECE_SIZE)||value.parts.length>MAX_PIECES)throw new Error('pieces');
  let total=0;
  value.parts.forEach((p,i)=>{
    if(!p||Object.keys(p).sort().join(',')!=='index,sha256,size'||!Number.isSafeInteger(p.index)||p.index!==i||
       !Number.isSafeInteger(p.size)||p.size<1||p.size>PIECE_SIZE||(i<value.parts.length-1&&p.size!==PIECE_SIZE)||
       (typeof p.sha256!=='string'||!/^[a-f0-9]{64}$/.test(p.sha256)))throw new Error('pieces');
    total+=p.size;
  });
  if(total!==descriptor.size)throw new Error('pieces');
  return value;
}

// Reject duplicate keys, including escaped aliases, before JSON.parse can hide them.
export function parseWireJSON(text) {
  if(typeof text!=='string'||new TextEncoder().encode(text).byteLength>INTERNAL_LIMIT)throw new Error('json');
  let i=0;
  const ws=()=>{while(/[\t\n\r ]/.test(text[i]??'x'))i++;};
  const string=()=>{const start=i;if(text[i++]!=='"')throw new Error('json');let escaped=false;while(i<text.length){const c=text[i++];if(c==='"'&&!escaped)return JSON.parse(text.slice(start,i));if(c.charCodeAt(0)<32)throw new Error('json');if(escaped)escaped=false;else if(c==='\\')escaped=true;}throw new Error('json');};
  function value(depth){ws();if(depth>24)throw new Error('json');const c=text[i];
    if(c==='{'){i++;ws();const keys=new Set();if(text[i]==='}'){i++;return;}while(true){ws();const key=string();if(keys.has(key))throw new Error('json');keys.add(key);ws();if(text[i++]!==':')throw new Error('json');value(depth+1);ws();if(text[i]==='}'){i++;return;}if(text[i++]!==',')throw new Error('json');}}
    else if(c==='['){i++;ws();if(text[i]===']'){i++;return;}while(true){value(depth+1);ws();if(text[i]===']'){i++;return;}if(text[i++]!==',')throw new Error('json');}}
    else if(c==='"')string();else{const start=i;while(i<text.length&&!/[\t\n\r ,}\]]/.test(text[i]))i++;if(start===i)throw new Error('json');JSON.parse(text.slice(start,i));}}
  value(0);ws();if(i!==text.length)throw new Error('json');return JSON.parse(text);
}
