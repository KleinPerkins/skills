// Synthetic SQLite/Static Assets harness adapted from the pinned Machine Monitor
// 4f26c15527ef6912434e3953de6169aed8244e28 request-handler fixture. No provider calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {randomBytes,createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import worker from '../delivery/worker.mjs';
import {profile,origin,access,manifest,validateDescriptor,pieceDescriptor,parseWireJSON,PIECE_SIZE,MAX_PIECES,WIRE_LIMIT,INTERNAL_LIMIT} from '../delivery/contract.mjs';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const A={app_id:'io.synthetic.alpha',bundle_id:'io.synthetic.alpha.bundle',team_id:'ABCDEFGHIJ',architecture:'arm64',minimum_macos:'26.0',data_schema_version:1,origin:'https://alpha.example.invalid'};
const B={app_id:'io.synthetic.beta',bundle_id:'io.synthetic.beta',team_id:'0123456789',architecture:'x86_64',minimum_macos:'15.0',data_schema_version:2,origin:'https://beta.example.invalid'};
function fixture(t){
 const db=new DatabaseSync(':memory:');t.after(()=>db.close());
 db.exec(readFileSync(new URL('../delivery/schema.sql',import.meta.url),'utf8'));
 const objects=new Map(),archive=Buffer.from('synthetic archive'),pkg=Buffer.from('synthetic package');
 const make=(p=A,channel='stable',release='release-1',bytes=archive)=>({schema:'private-distribution/release/v1',...Object.fromEntries(Object.entries(p).filter(([k])=>k!=='origin')),channel,version:'1.2.3',build:2,source_revision:'a'.repeat(40),qualification_id:'qualification-1',qualified:channel==='stable',archive:{path:`/v1/apps/${p.app_id}/releases/${release}/archive`,size:bytes.length,sha256:hash(bytes),ed25519_signature:Buffer.alloc(64).toString('base64')},first_install:{path:`/v1/apps/${p.app_id}/releases/${release}/package`,size:pkg.length,sha256:hash(pkg),ed25519_signature:Buffer.alloc(64).toString('base64')}});
 const put=(p=A,channel='stable',release='release-1',bytes=archive)=>{
  const value=make(p,channel,release,bytes);
  for(const [kind,data] of [['archive',bytes],['package',pkg]]){
   const descriptor=kind==='archive'?value.archive:value.first_install,rows=[];
   for(let offset=0;offset<data.length;offset+=PIECE_SIZE){const chunk=data.subarray(offset,offset+PIECE_SIZE),index=rows.length,digest=hash(chunk),path=`/_private/${p.app_id}/${release}/${kind}/${descriptor.sha256}/${index}-${digest}.part`;objects.set(path,chunk);rows.push({index,path,size:chunk.length,sha256:digest});}
   db.prepare('INSERT OR IGNORE INTO artifact_parts VALUES(?,?,?,?,?)').run(p.app_id,release,kind,descriptor.sha256,JSON.stringify(rows));
   db.prepare('INSERT OR IGNORE INTO artifact_protocols VALUES(?,?,?,?,?,?)').run(p.app_id,release,kind,descriptor.sha256,'private-distribution/artifact-parts/v2',PIECE_SIZE);
  }
  db.prepare('INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?)').run(p.app_id,release,channel,JSON.stringify(value),value.archive.sha256,value.archive.size,`${p.app_id}/${value.archive.sha256}.zip`,value.qualification_id,'{}');
  db.prepare('INSERT OR REPLACE INTO channels(app_id,channel,release_id,generation) VALUES(?,?,?,?)').run(p.app_id,channel,release,1);return value;
 };
 const grant=(name,p=A,channel='stable',owner=false,expires=Math.floor(Date.now()/1000)+3600)=>{
  const token=randomBytes(32).toString('base64url');
  db.prepare('INSERT INTO grants VALUES(?,?,?,?,?,?,?)').run(name,hash(token),name,Number(owner),expires,null,Math.floor(Date.now()/1000));
  db.prepare('INSERT INTO entitlements VALUES(?,?,?)').run(name,p.app_id,channel);return token;
 };
 put();put(A,'qualification','owner-release');put(B);
 const friend=grant('friend'),owner=grant('owner',A,'qualification',true),beta=grant('beta',B),expired=grant('expired',A,'stable',false,1),revoked=grant('revoked');
 db.prepare("UPDATE grants SET revoked_at=1 WHERE grant_id='revoked'").run();
 let primaryReads=0,assetReads=0,override=null;
 const env={RELEASE_PROFILE:JSON.stringify(A),DB:{withSession(mode){assert.equal(mode,'first-primary');primaryReads++;return{prepare(sql){return{bind(...params){return{async first(){const row=db.prepare(sql).get(...params)||null;return row&&override?override(row):row;}};}};}};}},ASSETS:{async fetch(request){assetReads++;const u=new URL(request.url);assert.ok([A.origin,B.origin].includes(u.origin));assert.equal(request.headers.get('Authorization'),null);assert.equal(request.headers.get('Cookie'),null);assert.equal(request.headers.get('Cloudflare-Workers-Version-Overrides'),null);const bytes=objects.get(u.pathname);return bytes?new Response(request.method==='HEAD'?null:bytes):new Response(null,{status:404});}}};
 const request=(path,token=friend,options={},binding=env,p=A)=>{const headers=new Headers(options.headers);if(token!==null)headers.set('Authorization','Bearer '+token);return worker.fetch(new Request(p.origin+path,{...options,headers}),binding);};
 const expect=async(path,token,status,options={},binding=env,p=A)=>{const r=await request(path,token,options,binding,p);assert.equal(r.status,status,path);assert.match(r.headers.get('Cache-Control'),/private.*no-store/);assert.equal(r.headers.get('Cloudflare-CDN-Cache-Control'),'no-store');assert.equal(r.headers.get('Access-Control-Allow-Origin'),null);assert.equal(r.headers.get('Location'),null);return r;};
 return{db,env,objects,archive,pkg,make,put,grant,friend,owner,beta,expired,revoked,request,expect,set override(fn){override=fn;},get primaryReads(){return primaryReads;},get assetReads(){return assetReads;}};
}
const feed=`/v1/apps/${A.app_id}/channels/stable/manifest`,artifact=`/v1/apps/${A.app_id}/releases/release-1/archive`,piece=artifact+'/parts/0';

test('closed profile and access contracts bind distinct synthetic products',()=>{
 assert.equal(profile(A),A);assert.equal(profile(B),B);
 const token=randomBytes(32).toString('base64url');
 const file={schema:'private-distribution/access/v1',app_id:A.app_id,origin:A.origin,token};
 assert.equal(access(file,A),file);assert.throws(()=>access(file,B));
 for(const p of [{...A,extra:true},{...A,app_id:'../wrong'},{...A,bundle_id:[]},{...A,team_id:'bad'},{...A,data_schema_version:true},{...A,architecture:'other'},{...A,origin:'https://public.r2.dev'},{...A,origin:A.origin+'/'}])assert.throws(()=>profile(p));
 for(const u of ['http://alpha.example.invalid','https://user:pass@alpha.example.invalid','https://alpha.example.invalid/path','https://alpha.example.invalid?x'])assert.throws(()=>origin(u));
 assert.throws(()=>access({...file,token:token.slice(0,-1)+'B'},A));
 assert.throws(()=>parseWireJSON('{"app_id":"a","\\u0061pp_id":"b"}'));
});

test('actual primary SQL authorizes manifest and access status on each request',async t=>{
 const f=fixture(t),before=f.primaryReads;
 const r=await f.expect(feed,f.friend,200);manifest(await r.json(),A,'stable','release-1');
 const response=await f.expect('/v1/access/check',f.friend,200,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({app_id:A.app_id,channel:'stable'})});
 assert.deepEqual(await response.json(),{schema:'private-distribution/access-status/v1',app_id:A.app_id,channel:'stable',grant_id:'friend',expires_at:f.db.prepare("SELECT expires_at FROM grants WHERE grant_id='friend'").get().expires_at});
 assert.equal(f.primaryReads,before+2);
});

test('tokens cannot cross product, origin, channel, owner, expiry, or revocation boundaries',async t=>{
 const f=fixture(t);
 for(const token of [null,'bad',f.expired,f.revoked,f.owner,f.beta])for(const path of [feed,artifact+'/parts',piece])await f.expect(path,token,401);
 const qual=`/v1/apps/${A.app_id}/channels/qualification/manifest`;
 await f.expect(qual,f.friend,401);await f.expect(qual,f.owner,200);
 await f.expect(`/v1/apps/${A.app_id}/releases/owner-release/archive/parts/0`,f.owner,200);
 await f.expect(`/v1/apps/${B.app_id}/channels/stable/manifest`,f.friend,401);
 const betaEnv={...f.env,RELEASE_PROFILE:JSON.stringify(B)};
 const bfeed=`/v1/apps/${B.app_id}/channels/stable/manifest`;
 manifest(await(await f.expect(bfeed,f.beta,200,{},betaEnv,B)).json(),B);
 await f.expect(bfeed,f.friend,401,{},betaEnv,B);
 await f.expect(feed,f.beta,400,{},betaEnv,A);
 assert.throws(()=>f.db.prepare('INSERT INTO entitlements VALUES(?,?,?)').run('friend',A.app_id,'qualification'));
});

test('bounded pieces and descriptors preserve original artifact identity',async t=>{
 const f=fixture(t),bytes=Buffer.alloc(PIECE_SIZE+7,3),release=f.put(A,'stable','multi',bytes),path=release.archive.path;
 const metadata=await(await f.expect(path+'/parts',f.friend,200)).text();assert.ok(Buffer.byteLength(metadata)<WIRE_LIMIT);
 const desc=pieceDescriptor(parseWireJSON(metadata),release.archive,A.app_id),chunks=[];
 for(const p of desc.parts){const r=await f.expect(path+'/parts/'+p.index,f.friend,200);const b=Buffer.from(await r.arrayBuffer());assert.equal(r.headers.get('Content-Length'),String(p.size));assert.equal(b.length,p.size);assert.equal(hash(b),p.sha256);chunks.push(b);}
 assert.equal(hash(Buffer.concat(chunks)),release.archive.sha256);
 const head=await f.expect(path+'/parts/1',f.friend,200,{method:'HEAD'});assert.equal(head.headers.get('Content-Length'),'7');assert.equal(await head.text(),'');
 await f.expect(path,f.friend,503);await f.expect(path+'/parts',f.friend,405,{method:'HEAD'});
 await f.expect(path+'/parts/2',f.friend,400);
 for(const index of ['01','-1','1.0','2047/extra'])await f.expect(path+'/parts/'+index,f.friend,404);
 const pkg=release.first_install;validateDescriptor(pkg,A.app_id,'multi','package');
 assert.equal(await(await f.expect(pkg.path+'/parts/0',f.friend,200)).text(),f.pkg.toString());
});

test('revocation and entitlement removal remain effective after metadata is warm',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const reads=f.primaryReads,assets=f.assetReads;
 f.db.prepare("UPDATE grants SET revoked_at=1 WHERE grant_id='friend'").run();
 for(const path of [feed,artifact+'/parts',piece])await f.expect(path,f.friend,401);
 assert.equal(f.primaryReads,reads+3);assert.equal(f.assetReads,assets);
 f.db.prepare("UPDATE grants SET revoked_at=NULL,expires_at=1 WHERE grant_id='friend'").run();await f.expect(piece,f.friend,401);
 f.db.prepare("UPDATE grants SET expires_at=? WHERE grant_id='friend'").run(Math.floor(Date.now()/1000)+3600);
 f.db.prepare("DELETE FROM entitlements WHERE grant_id='friend'").run();await f.expect(piece,f.friend,401);
});

test('no public package, private assets, page, or static fallback exists',async t=>{
 const f=fixture(t);
 for(const path of ['/', '/download.js','/package.zip','/unknown',...f.objects.keys()])for(const token of [null,f.friend])await f.expect(path,token,404);
 assert.equal(f.assetReads,0);
 for(const path of [piece,feed]){
  await f.expect(path,f.friend,403,{headers:{Origin:B.origin}});
  await f.expect(path,f.friend,403,{headers:{'Sec-Fetch-Site':'cross-site'}});
  await f.expect(path,f.friend,403,{headers:{'Cloudflare-Workers-Version-Overrides':'unsafe'}});
 }
 await f.expect(feed+'?token=ignored',f.friend,400);
 await f.expect(feed,f.friend,405,{method:'OPTIONS'});
 await f.expect(piece,f.friend,416,{headers:{Range:'bytes=0-1'}});
 await f.expect(piece,f.revoked,401,{headers:{Range:'bytes=0-1'}});
 await f.expect(piece,f.friend,400,{headers:{'If-None-Match':'anything'}});
});

test('strict small JSON access request rejects duplicates, extra fields and wrong types',async t=>{
 const f=fixture(t),options=body=>({method:'POST',headers:{'Content-Type':'application/json'},body});
 await f.expect('/v1/access/check',f.friend,400,options('{"app_id":"x","app_id":"'+A.app_id+'","channel":"stable"}'));
 await f.expect('/v1/access/check',f.friend,400,options('x'.repeat(1025)));
 for(const body of ['null','[]','{}',JSON.stringify({app_id:A.app_id,channel:'stable',url:B.origin}),JSON.stringify({app_id:A.app_id,channel:'qualification'})])await f.expect('/v1/access/check',f.friend,401,options(body));
 await f.expect('/v1/access/check',f.friend,400,{method:'POST',body:'{}'});
});

test('malformed runtime profile fails closed before DB or asset access',async t=>{
 const f=fixture(t);
 for(const raw of [undefined,'{}','null',JSON.stringify({...A,credential:'forbidden'}),JSON.stringify({...A,origin:'http://unsafe.invalid'}),'{"app_id":"duplicate","app_id":"other"}'])await f.expect(feed,f.friend,503,{}, {...f.env,RELEASE_PROFILE:raw});
 assert.equal(f.primaryReads,0);assert.equal(f.assetReads,0);
});

test('stale and malformed manifest row bindings never reach assets',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const assets=f.assetReads;
 for(const [key,value] of [['channel','qualification'],['release_id','other'],['archive_sha256','b'.repeat(64)],['archive_size',1],['object_key','wrong'],['manifest_json','null'],['manifest_json','x'.repeat(16385)]]){
  f.override=row=>({...row,[key]:value});await f.expect(piece,f.friend,503);
 }
 for(const change of [{team_id:B.team_id},{bundle_id:B.bundle_id},{app_id:B.app_id},{minimum_macos:'1'},{architecture:'universal'},{data_schema_version:2},{qualified:false},{extra:true}]){
  f.override=row=>({...row,manifest_json:JSON.stringify({...JSON.parse(row.manifest_json),...change})});await f.expect(piece,f.friend,503);
 }
 f.override=row=>({...row,manifest_json:row.manifest_json.replace('"version":"1.2.3"','"version":"9","version":"1.2.3"')});await f.expect(piece,f.friend,503);
 assert.equal(f.assetReads,assets);
});

test('corrupt part paths and schemas fail before any forwarding',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const before=f.assetReads;
 for(const path of ['https://foreign.invalid/file','//foreign.invalid/file','/_private/other/release/archive/x/0.part','/public/package.pkg']){
  f.override=row=>{const rows=JSON.parse(row.parts_json);rows[0].path=path;return{...row,parts_json:JSON.stringify(rows)};};
  await f.expect(piece,f.friend,503);await f.expect(piece,f.friend,503,{method:'HEAD'});
 }
 for(const value of ['[]','null',' '+f.db.prepare('SELECT parts_json FROM artifact_parts LIMIT 1').get().parts_json,'x'.repeat(INTERNAL_LIMIT+1)]){
  f.override=row=>({...row,parts_json:value});await f.expect(piece,f.friend,503);
 }
 for(const change of [{descriptor_schema:'private-distribution/artifact-parts/v1'},{part_size:1024*1024},{parts_json:'[{"index":0,"index":0}]'}]){
  f.override=row=>({...row,...change});await f.expect(piece,f.friend,503);
 }
 assert.equal(f.assetReads,before);
});

test('asset corruption, lengths, redirect and encoding failures return no artifact bytes',async t=>{
 const f=fixture(t);
 for(const bytes of [Buffer.alloc(f.archive.length,9),Buffer.alloc(f.archive.length-1),Buffer.alloc(f.archive.length+1)]){
  f.env.ASSETS={fetch:async()=>new Response(bytes)};const r=await f.expect(piece,f.friend,503);assert.deepEqual(await r.json(),{error:'service_unavailable'});
 }
 for(const [status,headers] of [[302,{Location:B.origin}],[200,{'Content-Length':'1'}],[200,{'Content-Encoding':'gzip'}],[404,{}],[429,{}]]){
  f.env.ASSETS={fetch:async()=>new Response(f.archive,{status,headers})};await f.expect(piece,f.friend,503);
 }
});

test('forwarded requests exclude client credentials and conditional headers',async t=>{
 const f=fixture(t);const source=f.env.ASSETS;
 f.env.ASSETS={fetch:async request=>{assert.equal([...request.headers].length,0);return source.fetch(request);}};
 await f.expect(piece,f.friend,200,{headers:{Cookie:'private=value','X-Client-Detail':'discard'}});
});

test('body read and binding timeout and caller cancellation release stream readers',async t=>{
 const f=fixture(t),timer=globalThis.setTimeout;t.after(()=>{globalThis.setTimeout=timer;});
 globalThis.setTimeout=(fn,ms,...args)=>timer(fn,ms===30000?2:ms,...args);
 f.env.ASSETS={fetch:()=>new Promise(()=>{})};await f.expect(piece,f.friend,503);
 let cancelled=0;
 f.env.ASSETS={fetch:async()=>new Response(new ReadableStream({start(c){c.enqueue(f.archive);},cancel(){cancelled++;}}))};await f.expect(piece,f.friend,503);assert.equal(cancelled,1);
 globalThis.setTimeout=timer;
 let started;const ready=new Promise(r=>started=r);cancelled=0;
 f.env.ASSETS={fetch:async()=>new Response(new ReadableStream({start(){started();},cancel(){cancelled++;}}))};
 const abort=new AbortController(),pending=f.request(piece,f.friend,{signal:abort.signal});await ready;abort.abort();assert.equal((await pending).status,503);assert.equal(cancelled,1);
});

test('metadata maximum remains bounded and canonical final part is retrievable',async t=>{
 const f=fixture(t),rid='r'.repeat(128),m=f.make(A,'stable',rid),last=Buffer.from('x');m.archive.size=(MAX_PIECES-1)*PIECE_SIZE+1;m.archive.sha256='a'.repeat(64);
 const rows=Array.from({length:MAX_PIECES},(_,index)=>({index,path:`/_private/${A.app_id}/${rid}/archive/${m.archive.sha256}/${index}-${hash(last)}.part`,size:index===MAX_PIECES-1?1:PIECE_SIZE,sha256:hash(last)}));
 f.db.prepare('INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?)').run(A.app_id,rid,'stable',JSON.stringify(m),m.archive.sha256,m.archive.size,`${A.app_id}/${m.archive.sha256}.zip`,m.qualification_id,'{}');
 f.db.prepare('INSERT INTO artifact_parts VALUES(?,?,?,?,?)').run(A.app_id,rid,'archive',m.archive.sha256,JSON.stringify(rows));
 f.db.prepare('INSERT INTO artifact_protocols VALUES(?,?,?,?,?,?)').run(A.app_id,rid,'archive',m.archive.sha256,'private-distribution/artifact-parts/v2',PIECE_SIZE);
 f.objects.set(rows.at(-1).path,last);
 const raw=await(await f.expect(m.archive.path+'/parts',f.friend,200)).text();assert.ok(Buffer.byteLength(raw)<WIRE_LIMIT);assert.equal(pieceDescriptor(parseWireJSON(raw),m.archive,A.app_id).parts.length,2048);
 assert.equal(await(await f.expect(m.archive.path+'/parts/2047',f.friend,200)).text(),'x');
 await f.expect(m.archive.path+'/parts/2048',f.friend,400);
});


test('stable pause denies retained artifact bytes while qualification readback stays available',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const before=f.assetReads;
 f.db.prepare("UPDATE channels SET release_id=NULL,generation=generation+1 WHERE app_id=? AND channel='stable'").run(A.app_id);
 await f.expect(feed,f.friend,401);await f.expect(artifact+'/parts',f.friend,401);await f.expect(piece,f.friend,401);await f.expect(piece,f.friend,401,{method:'HEAD'});
 assert.equal(f.assetReads,before);
 await f.expect(`/v1/apps/${A.app_id}/releases/owner-release/archive/parts/0`,f.owner,200);
 // A future authorized nonpaused channel again permits the retained immutable bytes.
 f.put(A,'stable','higher-build');await f.expect(piece,f.friend,200);
});


test('metadata cache never crosses a changed deployment profile identity',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const assets=f.assetReads;
 for(const change of [{team_id:B.team_id},{bundle_id:B.bundle_id},{architecture:B.architecture},{minimum_macos:B.minimum_macos},{data_schema_version:2}]){
  await f.expect(piece,f.friend,503,{}, {...f.env,RELEASE_PROFILE:JSON.stringify({...A,...change})});
 }
 assert.equal(f.assetReads,assets);await f.expect(piece,f.friend,200);
});

test('canonical part metadata rejects duplicate and escaped-equivalent complete fields',async t=>{
 const f=fixture(t);await f.expect(piece,f.friend,200);const before=f.assetReads;
 for(const transform of [raw=>raw.replace('"index":0','"index":0,"index":0'),raw=>raw.replace('"index":0','"index":0,"\\u0069ndex":0'),raw=>raw.replace('"index":0','"index":0.0'),raw=>raw.replace('"path"','"\\u0070ath"')]){
  f.override=row=>({...row,parts_json:transform(row.parts_json)});await f.expect(piece,f.friend,503);await f.expect(artifact+'/parts',f.friend,503);
 }
 assert.equal(f.assetReads,before);
});

test('cancellation releases the reader while the fixture producer completes its cleanup', async t => {
  const f=fixture(t);
  let notify, finishCancellation;
  const reading=new Promise(resolve=>{notify=resolve;});
  const cleanup=new Promise(resolve=>{finishCancellation=resolve;});
  const stream=new ReadableStream({
    highWaterMark:0,
    pull(){notify();},
    cancel(){return cleanup;},
  },{highWaterMark:0});
  f.env.ASSETS={fetch:async()=>new Response(stream)};
  const abort=new AbortController();
  const pending=f.request(piece,f.friend,{signal:abort.signal});
  let timer;
  try {
    await reading;
    abort.abort();
    const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Worker cleanup held its response')),500);});
    assert.equal((await Promise.race([pending,deadline])).status,503);
    assert.equal(stream.locked,false);
  } finally {
    clearTimeout(timer);
    finishCancellation();
  }
});
