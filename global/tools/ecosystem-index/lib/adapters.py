"""Explicit eligible inputs. No traversal, repository imports or processes."""
from __future__ import annotations
import configparser
import os
import re
import stat
from urllib.parse import urlsplit
from .contracts import (fail, Refusal, json_load, metadata, digest, safe_text,
                        encode, observation, relative, closed, string, guarded)
from .io_safe import read_file, directory


def normalize_remote(value):
    """Identity only: discard credentials/query/fragment; never follow a URL."""
    if value is None: return None
    if len(value)>2048 or any(ord(c)<32 for c in value): fail('ineligible_value')
    if '::' in value or value.startswith(('/', '.', '~', '-')): fail('ineligible_value')
    if '://' in value:
        try:
            p=urlsplit(value)
            if p.scheme not in {'https','http','ssh','git'} or not p.hostname: fail('ineligible_value')
            host=p.hostname.lower(); path=p.path
            if p.port: host+=':'+str(p.port)
        except ValueError: fail('ineligible_value')
    else:
        match=re.fullmatch(r'(?:[^/@:]+@)?([A-Za-z0-9.-]+):([^?#]+)(?:[?#].*)?',value)
        if not match: fail('ineligible_value')
        host=match.group(1).lower(); path=match.group(2)
    path=path.strip('/')
    if path.endswith('.git'): path=path[:-4]
    if not path or any(x in {'','.','..'} for x in path.split('/')) or not re.fullmatch(r'[A-Za-z0-9._/-]+',path):
        fail('ineligible_value')
    return host+'/'+path


def repository_identity(root):
    ident=root['identity']
    if ident is None: return None
    remote=normalize_remote(ident['remote'])
    if ident['provider']:
        normalized='provider:'+safe_text(ident['provider'],256)
    elif remote:
        normalized='remote:'+remote
    else:
        normalized='local:'+root['git']['common_dir'] if root['git'] else 'local:'+root['path']
    return normalized


def typed(kind,key):
    return kind+':'+digest(key.encode('utf-8'))


def yaml_load(data,validate=True):
    try:
        import yaml
    except ImportError:
        fail('parser_unavailable',3)
    class BoundedLoader(yaml.SafeLoader):
        def __init__(self,stream):
            super().__init__(stream); self.depth=0; self.nodes=0
        def compose_node(self,parent,index):
            if self.check_event(yaml.AliasEvent): fail('invalid_input')
            event=self.peek_event()
            if getattr(event,'tag',None) is not None: fail('invalid_input')
            self.depth+=1; self.nodes+=1
            if self.depth>20 or self.nodes>10000: fail('bound_exceeded')
            try: return super().compose_node(parent,index)
            finally: self.depth-=1
        def construct_mapping(self,node,deep=False):
            seen=set()
            for k,_ in node.value:
                key=self.construct_object(k,deep=deep)
                if type(key) is not str or key in seen: fail('invalid_input')
                seen.add(key)
            return super().construct_mapping(node,deep=deep)
    try:
        loader=BoundedLoader(data.decode('utf-8'))
        try:
            value=loader.get_single_data()
            return metadata(value) if validate else value
        finally: loader.dispose()
    except Refusal: raise
    except (yaml.YAMLError,UnicodeError,ValueError,TypeError,RecursionError): fail('invalid_input')


@guarded
def parse_metadata(data,adapter,fields,repository_id=None,capability_scope=None):
    if adapter=='json': value=metadata(json_load(data))
    elif adapter=='yaml': value=yaml_load(data)
    elif adapter=='capability-yaml':
        raw=yaml_load(data,False)
        allowed={'assets','descriptor_ref','expose','flavor','id','install','kind','owner',
                 'payload_digest','payload_version','post_mgmt','provenance_ref','provenance_source',
                 'provenance_trust','runtime_contract','schema','scope','shape','sync_policy'}
        closed(raw,{'schema','id','kind','flavor','scope','owner','install'},allowed)
        if raw['schema']!='kp-capability/v1': fail()
        if raw['kind'] not in {'skill','tool','rule','sub-agent','plugin'}: fail()
        if raw['scope'] not in {'global','project'} or type(raw['flavor']) is not int or raw['flavor'] not in {1,2}: fail()
        for key,value in raw.items():
            if key=='flavor': continue
            if key=='assets':
                # This owner field is a whitespace-separated scalar, never a
                # repository-controlled path list to open.
                string(value,4096,True)
            else: string(value,4096,True)
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]*',raw['id']): fail()
        if not repository_id: fail()
        cid='capability:'+repository_id.split(':',1)[1]+'/'+raw['kind']+'/'+raw['scope']+'/'+raw['id']
        value={'entities':[{'id':cid,'kind':'capability','title':raw['id']}]}
    elif adapter=='skill-frontmatter':
        # Parse only explicitly opted-in frontmatter, never the Markdown body.
        if not data.startswith(b'---\n'): fail()
        end=data.find(b'\n---\n',4)
        if end<0: fail()
        raw=yaml_load(data[4:end],False)
        closed(raw,{'name','description'})
        safe_text(raw['name'],128); safe_text(raw['description'],512)
        if not repository_id or capability_scope not in {'global','project'} or not re.fullmatch(r'[a-z0-9][a-z0-9-]*',raw['name']): fail()
        cid='capability:'+repository_id.split(':',1)[1]+'/skill/'+capability_scope+'/'+raw['name']
        value={'entities':[{'id':cid,'kind':'capability','title':raw['name'],'description':raw['description']}]}
    else: fail()
    for item in value['entities']:
        if item['kind']=='repository':
            if item['id']!=repository_id: fail()
            if any(edge['predicate']=='belongs_to' for edge in item.get('edges',[])): fail()
    allowed=set(fields)
    out=[]
    for item in value['entities']:
        # Noneligible recognized fields are not retained in the cache.
        out.append({k:v for k,v in item.items() if k in allowed|{'id','kind'}})
    return out


def identity_representations(root):
    ident=root['identity']
    if ident is None: return set()
    result={repository_identity(root),'local:'+root['path']}
    if ident['provider']: result.add('provider:'+ident['provider'])
    remote=normalize_remote(ident['remote'])
    if remote: result.add('remote:'+remote)
    if root['git']:
        result.update('local:'+root['git'][k] for k in ('common_dir','git_dir'))
    return result


def validate_git_pointer(raw, base, expected, *, prefix=''):
    """Compare one fixed Git pointer lexically without following its destination."""
    try:
        value = raw.decode('utf-8').rstrip('\r\n')
    except UnicodeError:
        fail('source_failed', 3)
    if not value.startswith(prefix):
        fail('source_failed', 3)
    value = value[len(prefix):]
    if not value or value != value.strip() or any(c in value for c in '\r\n\0'):
        fail('source_failed', 3)
    if os.path.normpath(os.path.join(base, value)) != expected:
        fail('source_failed', 3)


def git_records(root,repo_id,when,maximum,excluded,prior=None,*,reader=None):
    """Read only exact pre-authorized metadata paths; ignore config includes.

    Common/per-worktree paths are independent scopes supplied by the operator.
    There is no `git` process, ref traversal, discovery or command execution.
    """
    opener = directory if reader is None else reader.directory
    read = read_file if reader is None else reader.read_file
    g=root['git']
    if not g: return []
    probe_paths=[root['path']+'/.git',g['common_dir']+'/config']
    if g['common_dir']!=g['git_dir']:
        probe_paths.append(g['git_dir']+'/commondir')
        if reader is not None:
            probe_paths.append(g['git_dir']+'/gitdir')
    if any(excluded(p) for p in probe_paths): fail('excluded',3)
    for path in (g['common_dir'],g['git_dir']):
        if excluded(path): fail('excluded',3)
        with opener(path): pass
    common=g['common_dir']; work=g['git_dir']
    layout={'root':root['path'],'common_dir':common,'git_dir':work,'config':digest(encode(root))}
    # Verify the supplied physical layout without resolving arbitrary discovered
    # destinations. Unsupported forms are partial, never guessed.
    with opener(root['path']) as rootfd:
        try: marker=os.stat('.git',dir_fd=rootfd,follow_symlinks=False)
        except OSError: fail('source_failed',3)
    if stat.S_ISDIR(marker.st_mode):
        layout['marker']='directory'
        if work!=root['path']+'/.git': fail('source_failed',3)
    elif stat.S_ISREG(marker.st_mode):
        marker_data=read(root['path']+'/.git',4096)
        layout['marker']=digest(marker_data)
        try: line=marker_data.decode('utf-8').strip()
        except UnicodeError: fail('source_failed',3)
        if not line.startswith('gitdir: ') or '\n' in line: fail('source_failed',3)
        target=line[8:]
        if os.path.normpath(os.path.join(root['path'],target))!=work: fail('source_failed',3)
    else: fail('unsafe_path',3)
    if common!=work:
        commondir=read(work+'/commondir',4096)
        layout['commondir']=digest(commondir)
        try: target=commondir.decode('utf-8').strip()
        except UnicodeError: fail('source_failed',3)
        if '\n' in target or os.path.normpath(os.path.join(work,target))!=common: fail('source_failed',3)
        if reader is not None:
            reverse = read(work+'/gitdir',4096)
            validate_git_pointer(reverse, work, root['path']+'/.git')
            layout['reverse_gitdir'] = digest(reverse)
    data=read(common+'/config',maximum)
    layout['git_config']=digest(data)
    binding=digest(encode(layout))
    if prior and prior['digest']==binding:
        import copy
        records=copy.deepcopy(prior['records'])
        for item in records:
            for o in item['observations']: o.update(state='current',observed_at=when)
        return binding,records,True
    try:
        cfg=configparser.RawConfigParser(strict=True,interpolation=None)
        cfg.read_string(data.decode('utf-8'))
        if any(section.lower()=='include' or section.lower().startswith('includeif ') for section in cfg.sections()): fail('source_failed',3)
        url=cfg.get('remote "origin"','url',fallback=None)
        remote=normalize_remote(url)
    except (ValueError,UnicodeError,configparser.Error): fail('source_failed',3)
    prefix='inventory/'+root['key']+'/git/'
    obs=[]
    if remote:
        obs.append(('identity','remote:'+remote,'observed',prefix+'common/config',digest(data)))
    clone_id=typed('clone',common); work_id=typed('worktree',work+'\0'+root['path'])
    def entity(eid,kind,parent,location,pointer):
        values=[make_observation('location',location,'observed','git',pointer,None,digest(data),when)]
        return {'id':eid,'kind':kind,'parent':parent,'observations':values,'conflicts':[]}
    out=[entity(clone_id,'clone',repo_id,common,prefix+'common/config'),
         entity(work_id,'worktree',clone_id,root['path'],prefix+'worktree')]
    if obs:
        out.append({'id':repo_id,'kind':'repository','parent':None,
                    'observations':[make_observation(f,v,c,'git',p,None,d,when) for f,v,c,p,d in obs], 'conflicts':[]})
    return binding,out,False


def make_observation(field,value,classification,kind,pointer,revision,content_digest,when,state='current'):
    out={'field':field,'value':value,'classification':classification,'source_kind':kind,
         'pointer':pointer,'revision':revision,'digest':content_digest,'observed_at':when,'state':state}
    observation(out)
    return out
