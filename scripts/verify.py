#!/usr/bin/env python3
"""Skills source groups and exact-run CI aggregation, adapted from qualified Dev."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SHARDS = ('baseline', 'save-game', 'capability-tests')
IDENTITY_KEYS = ('repository','repository_id','event','revision','workflow_sha','run_id',
                 'run_attempt','ref','head_sha','base_sha','workflow_ref','workflow')
NAMES = ('KleinPerkins/skills',)
MAX_OUTPUT = 8 * 1024 * 1024
class ContractError(ValueError): pass
def require(ok, reason):
    if not ok: raise ContractError(reason)
def digest(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def closed(value, fields):
    require(isinstance(value,dict) and set(value)==set(fields.split()),'closed schema fields differ')
def parse(raw):
    def unique(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate JSON key');d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)
def policy(root=ROOT):
    raw=(root/'.github/ci-contract.json').read_bytes(); c=parse(raw)
    require(c['schema']=='skills-ci-contract/v1' and c['repository_id']==1461925043,'CI identity')
    require(c['repository_names']==list(NAMES) and c['shards']==list(SHARDS),'CI names/shards')
    require((c['workflow'],c['workflow_name'],c['required_check'],c['actions_app_id'],c['reviewer_app_id'])==('.github/workflows/ci.yml','CI','ci-required',15368,4217367),'CI producer/workflow')
    require(set(c['commands'])==set(SHARDS),'command owner mismatch')
    baseline=root/'.github/scripts/verify-skills.sh'
    require(digest(baseline.read_bytes())==c['baseline_sha256'],'full baseline drift: inspect and update its digest intentionally')
    occurrences=[(s,cmd['argv']) for s in SHARDS for cmd in c['commands'][s] if '.github/scripts/verify-skills.sh' in cmd['argv']]
    require(occurrences==[('baseline',['bash','.github/scripts/verify-skills.sh'])],'full baseline must run exactly once')
    mraw=(root/'.github/test-shards.json').read_bytes();m=parse(mraw)
    require(m['schema']=='skills-test-sharding/v1' and m['state']=='configured' and m['aggregate']=='ci-required','sharding not configured')
    require([s['id'] for s in m['shards']]==list(SHARDS),'shard topology differs')
    members=[]
    for row in m['shards']:
        closed(row,'id coverage timeout_seconds')
        require(type(row['timeout_seconds']) is int and 1<=row['timeout_seconds']<=1800,'timeout bound')
        require(row['coverage'] and row['coverage']==sorted(set(row['coverage'])),'missing/duplicate/unsorted coverage')
        require(all((root/p).is_file() and not (root/p).is_symlink() for p in row['coverage']),'coverage path missing/symlink')
        members+=row['coverage']
        for command in c['commands'][row['id']]:
            closed(command,'id argv')
            require(isinstance(command['id'],str) and command['id'] and isinstance(command['argv'],list) and command['argv'] and all(isinstance(a,str) and a for a in command['argv']),'invalid command')
    require(len(members)==len(set(members)),'duplicate coverage ownership')
    for folder,owner in [('global/skills/save-game/tests','save-game'),('global/skills/swarm/tests','capability-tests'),('global/plugins/keep-awake/tests','capability-tests'),('local/skills/continual-learning-consolidate/tests','capability-tests'),('scripts/tests','capability-tests')]:
        pattern='test_ci_delivery*.py' if folder=='scripts/tests' else 'test_*.py'
        found={str(p.relative_to(root)) for p in (root/folder).glob(pattern)}
        declared=set(next(s['coverage'] for s in m['shards'] if s['id']==owner))
        require(found and found<=declared,'test inventory differs from source: '+folder)
    return c,m,digest(raw+b'\0'+mraw)

def identity(environment):
    names=('GITHUB_REPOSITORY','GITHUB_REPOSITORY_ID','GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_REF','CI_HEAD_SHA','CI_BASE_SHA','GITHUB_WORKFLOW_REF','GITHUB_WORKFLOW')
    v={k:environment.get(n,'') for k,n in zip(IDENTITY_KEYS,names)}
    require(v['repository'] in NAMES and v['repository_id']=='1461925043','wrong repository phase/ID')
    require(v['event'] in ('push','pull_request','workflow_dispatch'),'unsupported CI event')
    for k in ('revision','workflow_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    for k in ('run_id','run_attempt'):require(re.fullmatch('[1-9][0-9]*',v[k]),'invalid '+k)
    if v['event']=='pull_request':
        require(re.fullmatch(r'refs/pull/[1-9][0-9]*/merge',v['ref']),'expected merge ref')
        for k in ('head_sha','base_sha'):require(re.fullmatch('[0-9a-f]{40}',v[k]),'invalid '+k)
    else:require(v['ref']=='refs/heads/main' and v['head_sha']==v['base_sha']=='','invalid main source tuple')
    require(v['workflow']=='CI' and v['workflow_sha']==v['revision'],'wrong tested workflow')
    require(v['workflow_ref']==v['repository']+'/.github/workflows/ci.yml@'+v['ref'],'workflow phase/path/ref mismatch')
    return v

def check_checkout(expected):
    require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==expected['revision'],'checkout differs')
    if expected['event']=='pull_request':
        require(subprocess.check_output(['git','show','-s','--format=%P','HEAD'],cwd=ROOT,text=True).split()==[expected['base_sha'],expected['head_sha']],'merge parent ordering differs')

def bounded(argv,timeout,cwd=ROOT,home=None):
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if home:
        env.update(HOME=home,XDG_STATE_HOME=home+'/state',XDG_CONFIG_HOME=home+'/config',GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    for k in list(env):
        # Shell startup files/functions can silently displace fixture PATH stubs.
        if k.startswith(('GIT_', 'BASH_FUNC_')) or k in ('BASH_ENV', 'ENV',
                'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'):
            env.pop(k)
    env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1')
    p=subprocess.Popen(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
    out=bytearray();selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ);deadline=time.monotonic()+timeout
    try:
        while selector.get_map():
            require(time.monotonic()<deadline,'command timeout')
            for key,_ in selector.select(min(.25,max(0,deadline-time.monotonic()))):
                data=os.read(key.fileobj.fileno(),65536)
                if not data:selector.unregister(key.fileobj);continue
                out.extend(data);require(len(out)<=MAX_OUTPUT,'command output exceeded bound')
        p.wait(timeout=max(.1,deadline-time.monotonic()))
        require(p.returncode==0,'command failed: '+str(argv)+'\n'+out.decode(errors='replace'))
        return bytes(out)
    finally:
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        try:p.wait(timeout=2)
        except subprocess.TimeoutExpired:pass
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        p.wait();selector.close();p.stdout.close()

def measured(shard):
    c,m,hash_=policy();row=next(s for s in m['shards'] if s['id']==shard)
    deadline=time.monotonic()+row['timeout_seconds'];logs=[]
    with tempfile.TemporaryDirectory(prefix='skills-ci-home-') as home:
        for cmd in c['commands'][shard]:
            out=bounded(cmd['argv'],max(1,deadline-time.monotonic()),home=home)
            print(out.decode(errors='replace'))
            require(b'Ran 0 tests' not in out,'empty test discovery')
            logs.append({'id':cmd['id'],'sha256':digest(out)})
    return {'commands':[x['id'] for x in c['commands'][shard]],'coverage':row['coverage'],'logs_sha256':digest(canonical(logs)),'contract_sha256':hash_}

def validate_measurement(value,shard,c,m,hash_):
    closed(value,'commands coverage logs_sha256 contract_sha256')
    row=next(s for s in m['shards'] if s['id']==shard)
    require(value['coverage']==row['coverage'] and value['commands']==[x['id'] for x in c['commands'][shard]] and value['contract_sha256']==hash_,'stale command/coverage/contract')
    require(isinstance(value['logs_sha256'],str) and re.fullmatch('[0-9a-f]{64}',value['logs_sha256']),'log digest missing')

def validate_aggregate(needs,expected):
    c,m,hash_=policy()
    require(isinstance(needs,dict) and set(needs)==set(SHARDS),'missing or extra shard')
    for shard in SHARDS:
        row=needs[shard];closed(row,'result outputs');require(row['result']=='success','shard failed/skipped/cancelled')
        closed(row['outputs'],'receipt');receipt=parse(row['outputs']['receipt']);closed(receipt,'schema shard identity result measurement')
        require(receipt['schema']=='skills-ci-shard/v1' and receipt['shard']==shard and receipt['identity']==expected and receipt['result']=='success','stale shard receipt')
        validate_measurement(receipt['measurement'],shard,c,m,hash_)
    return hash_

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('local','shard','aggregate'));p.add_argument('--shard',choices=SHARDS);a=p.parse_args()
    if a.mode=='local':
        for shard in (a.shard,) if a.shard else SHARDS:
            result=measured(shard);print(json.dumps({'shard':shard,'measurement':result},sort_keys=True))
        print('Local source checks passed; hosted/account/App/installed-host qualification is separate');return
    expected=identity(dict(os.environ));check_checkout(expected)
    if a.mode=='shard':
        require(a.shard is not None,'shard required');measurement=measured(a.shard)
        output=os.environ.get('GITHUB_OUTPUT');require(output,'GITHUB_OUTPUT required')
        receipt={'schema':'skills-ci-shard/v1','shard':a.shard,'identity':expected,'result':'success','measurement':measurement}
        with open(output,'a') as f:f.write('receipt='+canonical(receipt).decode()+'\n')
    else:
        require(a.shard is None,'aggregate cannot select shard');hash_=validate_aggregate(parse(os.environ.get('CI_NEEDS','null')),expected)
        print('SKILLS_CI_AGGREGATE_V1 '+canonical({'schema':'skills-ci-aggregate/v1','identity':expected,'result':'success','contract_sha256':hash_}).decode())
if __name__=='__main__':
    try:main()
    except (ContractError,ValueError,OSError,subprocess.SubprocessError,KeyError,TypeError) as e:
        print('CI verification refused: '+str(e),file=sys.stderr);sys.exit(1)
