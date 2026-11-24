"""Explicit refresh and deterministic snapshot-only queries."""
from __future__ import annotations
import copy
import os
import re
import time
from datetime import datetime,timezone
from .contracts import (Refusal, fail, config, json_load, snapshot, encode, digest,
                        now, timestamp, integer, entity_id, INPUT_MAX, FIELDS, result as validate_result)
from .deadline import deadline, tighten
from .io_safe import read_file, load_snapshot, Publisher, directory, outside_repositories
from .receipt_store import AdmittedPublisher
from .checkout_admission import validate_input_diagnostics
from .adapters import (repository_identity, normalize_remote, typed, parse_metadata,
                       make_observation, git_records, identity_representations)


def _mark(records,state):
    result=copy.deepcopy(records)
    for e in result:
        for o in e['observations']:
            if o['state']!='missing' or state=='missing': o['state']=state
    return result


def _merge(records):
    entities={}
    for e in records:
        if e['id'] not in entities: entities[e['id']]=copy.deepcopy(e)
        else:
            dest=entities[e['id']]
            dest['conflicts']=sorted(set(dest['conflicts'])|set(e['conflicts']))
            if dest['parent']!=e['parent']:
                # Parent observations are represented as declared belongs_to edges,
                # so conflicting source owners remain explicit and inspectable.
                dest['conflicts']=sorted(set(dest['conflicts'])|{'parent'})
            for o in e['observations']:
                if o not in dest['observations']: dest['observations'].append(copy.deepcopy(o))
    for e in entities.values():
        byfield={}
        for o in e['observations']:
            if o['state']=='missing': continue
            byfield.setdefault(o['field'],set()).add(encode(o['value']))
        conflicts={k for k,v in byfield.items() if len(v)>1 and k not in {'aliases','pointers','edges','location','identity'}}
        identity_groups={}
        for o in e['observations']:
            if o['field']=='identity' and o['state']!='missing':
                identity_groups.setdefault(o['value'].partition(':')[0],set()).add(o['value'])
        if any(len(group)>1 for group in identity_groups.values()): conflicts.add('identity')
        e['conflicts']=sorted(set(e['conflicts'])|conflicts)
        e['observations'].sort(key=lambda o:(o['pointer'],o['field'],o['classification'],o['digest']))
    return sorted(entities.values(),key=lambda e:e['id'])


def refresh(config_path,cache_path,*,clock=time.monotonic,before_replace=None):
    with deadline(60):
        return _refresh(config_path,cache_path,clock=clock,before_replace=before_replace)


def refresh_admitted(config_path, cache_path, admission, *, before_replace=None):
    admission.validate()
    with deadline(60):
        return _refresh(config_path, cache_path, before_replace=before_replace, admission=admission)


def _refresh(config_path,cache_path,*,clock=time.monotonic,before_replace=None,admission=None):
    start=clock()
    outside_repositories(os.path.dirname(config_path))
    config_bytes = read_file(config_path, INPUT_MAX, True)
    if admission and digest(config_bytes) != admission.config_digest:
        fail('invalid_input')
    cfg=config(json_load(config_bytes))
    tighten(cfg['bounds']['refresh_seconds'])
    if os.path.normpath(config_path)==os.path.normpath(cache_path): fail('unsafe_path',3)
    # State may not live within an explicitly indexed location, even if it has
    # no .git marker (e.g. a caller-supplied native project observation).
    for r in cfg['roots']:
        for p in (config_path,cache_path):
            if p==r['path'] or p.startswith(r['path']+'/'): fail('unsafe_path',3)
    def excluded(path):
        return any(path==p or path.startswith(p+'/') for p in cfg['exclude_paths'])
    def budget():
        if clock()-start>cfg['bounds']['refresh_seconds']: fail('bound_exceeded',3)
    publisher_class = AdmittedPublisher if admission else Publisher
    with publisher_class(cache_path,cfg['bounds']['snapshot_bytes']) as publisher:
        try: old=load_snapshot(cache_path)
        except Refusal:
            # Absence may start a cache. Corruption must not silently discard facts.
            try: os.stat(publisher.name,dir_fd=publisher.fd,follow_symlinks=False)
            except FileNotFoundError: old=None
            else: fail('unavailable',3)
        old_inputs={x['key']:x for x in old['inputs']} if old else {}
        inputs=[]; reasons=set(); parsed=0; reused=0; when=now()
        used_checkouts = set()
        current_checkouts = set()
        input_diagnostics = {}

        def target_read(root, locations, collect):
            if admission is None:
                return collect()
            return admission.read(root['path'], locations, collect)

        def inspect_root(path, reader):
            opener = directory if reader is None else reader.directory
            with opener(path):
                pass

        def metadata_read(path, reader):
            read = read_file if reader is None else reader.read_file
            return read(path, cfg['bounds']['input_bytes'])

        def note(key, reason, state=None):
            if admission is not None:
                input_diagnostics[key] = {"reason":reason, "state":state or (
                    "omitted" if reason == "excluded" else "unavailable")}

        def skip_root(root, key, reason):
            reasons.add(reason)
            note(key, reason)
            if root['git']:
                note(key+'/git', reason)
            for source in root['sources']:
                file_reason = 'excluded' if excluded(root['path']+'/'+source['path']) else reason
                note(key+'/'+source['path'], file_reason)
        def authorization(root, source=None, adapter='inventory'):
            # This is authorization scope, separate from input content and field
            # eligibility. A reused key alone can never authorize old facts.
            scope={'path':root['path'],'identities':sorted(identity_representations(root)),
                   'git':root['git'],'scope':root['scope'],'inventory':root['inventory'],
                   'exclude_paths':sorted(cfg['exclude_paths']),
                   'exclude_identities':sorted(cfg['exclude_identities'])}
            scope['source']={k:source[k] for k in ('path','adapter','kind','capability_scope') if k in source} if source else {'adapter':adapter}
            return digest(encode(scope))

        def prior_input(key, auth):
            prior=old_inputs.get(key)
            return prior if prior and prior['authorization_digest']==auth else None

        def retain(key, auth, reason, eligible=None):
            reasons.add(reason)
            prior=prior_input(key,auth)
            note(key, reason, "stale" if prior is not None else None)
            if prior is not None:
                old_input=copy.deepcopy(prior); old_input['state']='stale'
                old_input['records']=_mark(old_input['records'],'stale')
                if eligible is not None:
                    for entity in old_input['records']:
                        kept=[]
                        for observation in entity['observations']:
                            owner_edge=[{'predicate':'belongs_to','target':entity['parent'],'classification':'declared','pointer':observation['pointer']}]
                            if observation['field'] in eligible or (entity['kind']!='repository' and observation['field']=='edges' and observation['value']==owner_edge):
                                kept.append(observation)
                        entity['observations']=kept
                        entity['conflicts']=[f for f in entity['conflicts'] if f in eligible or f=='parent']
                inputs.append(old_input)

        def retain_sources(root,key,reason):
            for source in root['sources']:
                if excluded(root['path']+'/'+source['path']):
                    reasons.add('excluded'); note(key+'/'+source['path'], 'excluded'); continue
                retain(key+'/'+source['path'],authorization(root,source),reason,set(source['fields']))

        for root in cfg['roots']:
            budget()
            key='inventory/'+root['key']
            # External inventory exclusions are enforceable before root access.
            # A stale inventory's contradictory Git origin can only be detected
            # by the separately permitted fixed metadata probe below.
            scopes=[root['path']]+(list(root['git'].values()) if root['git'] else [])
            if any(excluded(p) for p in scopes): skip_root(root,key,'excluded'); continue
            if root['scope']!='permitted' or root['identity'] is None:
                skip_root(root,key,'unknown_scope'); continue
            identity=repository_identity(root)
            if identity_representations(root) & set(cfg['exclude_identities']):
                skip_root(root,key,'excluded'); continue
            rid=typed('repository',identity)
            bind=digest(encode(root)); root_auth=authorization(root)
            base=[{'id':rid,'kind':'repository','parent':None,'observations':[
                make_observation('identity',identity,'declared',root['inventory'],key,None,bind,when),
                make_observation('location',root['path'],'declared',root['inventory'],key,None,bind,when)],'conflicts':[]}]
            remote=normalize_remote(root['identity']['remote'])
            if remote and identity!='remote:'+remote:
                base[0]['observations'].append(make_observation('identity','remote:'+remote,'declared',root['inventory'],key,None,bind,when))
            for field in ('title','aliases'):
                if field in root['storage_fields']:
                    base[0]['observations'].append(make_observation(field,root[field],'declared',root['inventory'],key,None,bind,when))
            try:
                target_read(root, (('checkout', root['path']),), lambda reader=None: inspect_root(root['path'], reader))
            except Refusal as exc:
                if admission and exc.code == 'excluded':
                    skip_root(root,key,'excluded'); continue
                used_checkouts.add(root['path'])
                retain(key,root_auth,'source_failed',set(root['storage_fields'])|{'identity','location'})
                retain_sources(root,key,'source_failed')
                if root['git']: retain(key+'/git',authorization(root,adapter='git'),'source_failed')
                continue

            git_input=None; identity_conflict=False
            if root['git']:
                gkey=key+'/git'; git_auth=authorization(root,adapter='git')
                try:
                    budget()
                    locations = (('checkout', root['path']), ('git_directory', root['git']['git_dir']),
                                 ('common_directory', root['git']['common_dir']))
                    if admission is not None and root['git']['git_dir'] != root['git']['common_dir']:
                        work = root['git']['git_dir']
                        locations += (('linked_gitfile', root['path']+'/.git'),
                                      ('linked_common_pointer', work+'/commondir'),
                                      ('linked_reverse_pointer', work+'/gitdir'))
                    binding,records,was_reused=target_read(root, locations, lambda reader=None: git_records(
                        root,rid,when,cfg['bounds']['input_bytes'],excluded,prior_input(gkey,git_auth),reader=reader))
                    observed={o['value'] for entity in records for o in entity['observations']
                              if o['field']=='identity' and o['source_kind']=='git' and o['state']=='current'}
                    if observed & set(cfg['exclude_identities']):
                        # Nothing from this root, including prior inventory or
                        # source facts, survives a discovered excluded identity.
                        skip_root(root,key,'excluded'); continue
                    observed_remote=next(iter(observed),None)
                    if observed_remote is None and (remote or root['identity']['provider']):
                        fail('unknown_scope',3)
                    # A remote-less declared local root cannot be silently grouped
                    # with a newly discovered remote, nor can one remote stand in
                    # for a contradictory declared remote.
                    identity_conflict=(observed_remote is not None and (remote is None or observed_remote!='remote:'+remote))
                    if identity_conflict:
                        reasons.add('source_failed'); base[0]['conflicts']=['identity']
                        note(key, 'source_failed', 'conflict')
                    reused+=int(was_reused); parsed+=int(not was_reused)
                    git_input={'key':gkey,'digest':binding,'authorization_digest':git_auth,'state':'current','records':records}
                except Refusal as exc:
                    if admission and exc.code == 'excluded':
                        skip_root(root,key,'excluded'); continue
                    used_checkouts.add(root['path'])
                    retain(key,root_auth,exc.code,set(root['storage_fields'])|{'identity','location'})
                    retain(gkey,git_auth,exc.code)
                    retain_sources(root,key,exc.code)
                    # Unknown/failed fixed Git metadata is never permission to
                    # mine the tree under an unverified cached identity.
                    continue
            used_checkouts.add(root['path'])
            current_checkouts.add(root['path'])
            inputs.append({'key':key,'digest':bind,'authorization_digest':root_auth,'state':'current','records':base})
            if git_input:
                inputs.append(git_input)
            if identity_conflict:
                retain_sources(root,key,'source_failed')
                continue

            for source in root['sources']:
                budget(); skey=key+'/'+source['path']; source_auth=authorization(root,source)
                path=root['path']+'/'+source['path']
                if excluded(path): reasons.add('excluded'); note(skey,'excluded'); continue
                try:
                    data=target_read(root, (('source', path),),
                                     lambda reader=None: metadata_read(path, reader))
                    binding=digest(data+encode({'source':source,'root':bind}))
                    prior=prior_input(skey,source_auth)
                    if source['adapter'] in {'yaml','capability-yaml','skill-frontmatter'}:
                        try: __import__('yaml')
                        except ImportError: fail('parser_unavailable',3)
                    if prior and prior['digest']==binding:
                        records=copy.deepcopy(prior['records'])
                        for entity in records:
                            for observation in entity['observations']:
                                if observation['state']!='missing': observation.update(state='current',observed_at=when)
                        reused+=1
                    else:
                        values=parse_metadata(data,source['adapter'],source['fields'],rid,source.get('capability_scope')); parsed+=1
                        records=[]
                        for item in values:
                            observations=[]
                            for field,value in item.items():
                                if field in FIELDS:
                                    observations.append(make_observation(field,value,'declared',source['kind'],skey,source['revision'],digest(data),when))
                            parent=None if item['kind']=='repository' else rid
                            if parent is not None:
                                observations.append(make_observation('edges',[{'predicate':'belongs_to','target':rid,'classification':'declared','pointer':skey}],
                                                                     'declared',source['kind'],skey,source['revision'],digest(data),when))
                            records.append({'id':item['id'],'kind':item['kind'],'parent':parent,'observations':observations,'conflicts':[]})
                        if prior:
                            present={entity['id'] for entity in records}
                            missing=_mark([entity for entity in prior['records'] if entity['id'] not in present],'missing')
                            for entity in missing:
                                entity['observations']=[o for o in entity['observations'] if o['field'] in set(source['fields'])]
                                entity['conflicts']=[f for f in entity['conflicts'] if f in set(source['fields'])]
                            records.extend(missing)
                    inputs.append({'key':skey,'digest':binding,'authorization_digest':source_auth,'state':'current','records':records})
                except Refusal as exc:
                    if admission and exc.code == 'excluded':
                        reasons.add('excluded'); note(skey,'excluded')
                    else:
                        retain(skey,source_auth,exc.code,set(source['fields']))
        budget()
        entities=_merge([e for i in inputs for e in i['records']])
        if len(entities)>cfg['bounds']['entities']: fail('bound_exceeded',3)
        value={'schema':'ecosystem-index/snapshot/v1','generation':old['generation']+1 if old else 1,
               'observed_at':when,'coverage':'partial' if reasons else 'complete',
               'inputs':inputs,'entities':entities,'reasons':sorted(reasons)}
        snapshot(value); budget()
        if admission:
            validate_input_diagnostics(input_diagnostics, value['inputs'])
        def publication_gate():
            budget()
            if before_replace: before_replace()
            budget()
        def result_for(data):
            return validate_result({'schema':'ecosystem-index/result/v1','command':'refresh','status':value['coverage'],
                    'coverage':value['coverage'],'reasons':sorted(reasons),'generation':value['generation'],
                    'snapshot_digest':digest(data),'counts':{'entities':len(entities),'parsed':parsed,'reused':reused}})
        def commit(replace, data):
            receipt = admission.receipt(result_for(data), when, input_diagnostics)
            def publish_pair(verify_current):
                publisher.save_receipt(admission, receipt)
                verify_current()
                return replace()
            return admission.publish(tuple(sorted(used_checkouts)), frozenset(current_checkouts), publish_pair)
        data=publisher.publish(value,publication_gate,commit=commit if admission else None)
        result = result_for(data)
        return admission.receipt(result, when, input_diagnostics) if admission else result


# Selective reuse from the previous scorer: token sets, conservative singulars
# and additive, explainable field overlap. No routing/permission or raw prose signals.
def tokens(text):
    result=set()
    for token in re.findall(r'[a-z0-9]+',text.lower()):
        if len(token)>4 and token.endswith('ies'): token=token[:-3]+'y'
        elif len(token)>3 and token.endswith('s') and not token.endswith('ss'): token=token[:-1]
        if token not in {'the','and','for','with','how','find','use','a','an','to'}: result.add(token)
    return result


def freshness(value,at=None):
    at=at or datetime.now(timezone.utc)
    age=(at-timestamp(value['observed_at'])).total_seconds()
    if age<0: fail('unavailable',3)
    return {'observed_at':value['observed_at'],'age_seconds':age,'advisory_stale':age>86400,'advisory_after_seconds':86400}



def _context_owners(entities, found):
    """Resolve the logical owner in at most two parent hops, with cycle checks.

    Every visited entity may contribute pointer evidence, but only a unique,
    valid repository root can become source_owner. Conflicts at any hop keep
    the packet ambiguous; no first-parent guess is exposed.
    """
    by_id={entity['id']:entity for entity in entities}
    visited=set(); repositories=set(); ambiguous=False
    pending=[(found['id'],0,frozenset())]
    while pending:
        eid,hops,ancestors=pending.pop()
        if eid in ancestors:
            ambiguous=True; continue
        if eid in visited: continue
        visited.add(eid)
        entity=by_id.get(eid)
        if entity is None:
            ambiguous=True; continue
        parents={entity['parent']} if entity['parent'] else set()
        for observation in entity['observations']:
            if observation['field']=='edges' and observation['state']!='missing':
                parents.update(edge['target'] for edge in observation['value']
                               if edge['predicate']=='belongs_to' and edge['classification'] in {'declared','observed'})
        if {'parent','identity'} & set(entity['conflicts']) or len(parents)>1: ambiguous=True
        if entity['kind']=='repository':
            repositories.add(eid)
            if parents: ambiguous=True
        elif not parents:
            ambiguous=True
        for parent in sorted(parents,reverse=True):
            if parent in ancestors or parent==eid:
                ambiguous=True
            elif hops>=2:
                ambiguous=True
            else:
                pending.append((parent,hops+1,ancestors|{eid}))
    if len(repositories)!=1: ambiguous=True
    owner=None if ambiguous else next(iter(repositories))
    return visited,owner,ambiguous

def query(value,command,*,text=None,id=None,limit=5):
    snapshot(value)
    queried_at=datetime.now(timezone.utc)
    if any(timestamp(o['observed_at'])>queried_at for e in value['entities'] for o in e['observations']):
        fail('unavailable',3)
    result={'schema':'ecosystem-index/result/v1','command':command,'status':'none',
            'coverage':value['coverage'],'reasons':value['reasons'],'freshness':freshness(value,queried_at)}
    if command=='search':
        integer(limit,1,20)
        if type(text) is not str or len(text.encode('utf-8'))>4096: fail('bound_exceeded')
        terms=tokens(text); ranked=[]
        for e in value['entities']:
            if not any(o['state']!='missing' for o in e['observations']): continue
            contributions={}
            if text.strip()==e['id']: contributions['exact_id']=10000
            for field,weight in [('title',12),('aliases',18),('description',3),('identity',2)]:
                hits=set(); exact=False
                for o in e['observations']:
                    if o['field']!=field or o['state']=='missing': continue
                    parts=o['value'] if type(o['value']) is list else [o['value']]
                    for part in parts:
                        hits |= terms & tokens(part)
                        if text.strip() and text.strip().casefold()==part.casefold(): exact=True
                if hits: contributions[field]=weight*len(hits)+(100 if exact and field in {'title','aliases'} else 0)
            score=sum(contributions.values())
            if score: ranked.append({'entity':e,'score':score,'contributions':contributions})
        ranked.sort(key=lambda c:(-c['score'],c['entity']['id']))
        if ranked:
            result['status']='ambiguous' if len(ranked)>1 and ranked[0]['score']==ranked[1]['score'] else 'matches'
        result['candidates']=ranked[:limit]
        result['truncated']=len(ranked)>limit
    elif command in {'describe','context'}:
        entity_id(id)
        found=next((e for e in value['entities'] if e['id']==id),None)
        if command=='describe':
            result['entity']=found
            result['locations']=[]
            if found:
                ids={id}
                for _ in range(2): ids|={e['id'] for e in value['entities'] if e['parent'] in ids}
                result['locations']=[e for e in value['entities'] if e['id'] in ids and e['kind'] in {'clone','worktree'}]
        else:
            pointers=[]; relationships=[]; owner=None; ambiguous_owner=False
            if found:
                owners,owner,ambiguous_owner=_context_owners(value['entities'],found)
                pointer_groups=[]; relationship_groups=[]
                for e in value['entities']:
                    if e['id'] not in owners: continue
                    entity_pointers=[]; entity_relationships=[]
                    for o in e['observations']:
                        provenance={k:v for k,v in o.items() if k not in {'field','value'}}
                        if o['field']=='pointers':
                            entity_pointers.extend({'entity_id':e['id'],'pointer':p,'provenance':provenance} for p in o['value'])
                        elif o['field']=='edges':
                            entity_relationships.extend({'source':e['id'],'edge':edge,'provenance':provenance} for edge in o['value'])
                    pointer_groups.append(entity_pointers); relationship_groups.append(entity_relationships)
                # Interleave owners so one owner's many pointers cannot hide a
                # second owner's evidence within the bounded context packet.
                def interleave(groups):
                    return [group[index] for index in range(max((len(g) for g in groups),default=0))
                            for group in groups if index<len(group)]
                pointers=interleave(pointer_groups); relationships=interleave(relationship_groups)
            result.update(entity_id=id,source_owner=owner,
                          pointers=pointers[:20],relationships=relationships[:100],truncated=len(pointers)>20 or len(relationships)>100)
            if ambiguous_owner: result['status']='ambiguous'
        if found and result['status']!='ambiguous': result['status']='matches'
    else: fail()
    return validate_result(result)


def search(cache_path,text,limit=5): return query(load_snapshot(cache_path),'search',text=text,limit=limit)
def describe(cache_path,id): return query(load_snapshot(cache_path),'describe',id=id)
def context(cache_path,id): return query(load_snapshot(cache_path),'context',id=id)
