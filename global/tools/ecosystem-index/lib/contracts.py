"""Closed, bounded v1 records shared by the library and CLI."""
from __future__ import annotations
import hashlib
import functools
import json
import re
from datetime import datetime, timezone

INPUT_MAX = 262144
SNAPSHOT_MAX = 20971520
FIELDS = {'title', 'description', 'aliases', 'pointers', 'edges'}
KINDS = {'repository', 'capability', 'clone', 'worktree'}
REASONS = {'invalid_input', 'unavailable', 'busy', 'unsafe_path', 'excluded', 'unknown_scope',
           'source_failed', 'parser_unavailable', 'ineligible_value', 'bound_exceeded', 'interrupted'}

class Refusal(Exception):
    def __init__(self, code='invalid_input', exit_code=2):
        self.code = code if code in REASONS else 'invalid_input'
        self.exit_code = exit_code
        super().__init__(self.code)


def fail(code='invalid_input', exit_code=2):
    raise Refusal(code, exit_code)



def guarded(function):
    @functools.wraps(function)
    def validate(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Refusal:
            raise
        except (TypeError, ValueError, KeyError, RecursionError, OverflowError):
            fail()
    return validate


def closed(obj, required, optional=()):
    if type(obj) is not dict or set(obj) - set(required) - set(optional) or set(required) - set(obj):
        fail()
    return obj


def seq(value, maximum):
    if type(value) is not list or len(value) > maximum:
        fail('bound_exceeded')
    return value


def string(value, maximum=512, empty=False):
    if type(value) is not str or len(value) > maximum or (not value and not empty):
        fail()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail('ineligible_value')
    return value


def safe_text(value, maximum=512, empty=False):
    string(value, maximum, empty)
    # Eligibility is supplied separately by the closed field allowlist. These are
    # additional refusal checks, not a claim that a keyword filter proves privacy.
    if re.search(r'(?i)(?:-----BEGIN |(?:password|secret|token|api[_ -]?key)\s*[:=]|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{8,}|ignore (?:all |previous )?instructions|<script|\$\(|`)', value):
        fail('ineligible_value')
    return value


def strings(value, maximum=32):
    return [safe_text(x, 256) for x in seq(value, maximum)]


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail()
    return value


def timestamp(value):
    string(value, 64)
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            fail()
        return dt
    except (ValueError, OverflowError):
        fail()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def json_load(data, maximum=INPUT_MAX):
    if len(data) > maximum:
        fail('bound_exceeded')
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                fail()
            out[k] = v
        return out
    try:
        obj = json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                         parse_constant=lambda _: fail())
        bounded_tree(obj)
        return obj
    except (ValueError, UnicodeError, RecursionError, MemoryError):
        fail()


def bounded_tree(obj, depth=0, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if depth > 24 or counter[0] > 200000:
        fail('bound_exceeded')
    if type(obj) is dict:
        for k, v in obj.items():
            if type(k) is not str:
                fail()
            bounded_tree(v, depth+1, counter)
    elif type(obj) is list:
        for v in obj:
            bounded_tree(v, depth+1, counter)
    elif type(obj) not in (str, int, bool, type(None)):
        fail()


def entity_id(value):
    safe_text(value, 256)
    if not re.fullmatch(r'(repository|capability|clone|worktree):[A-Za-z0-9._:/-]+', value):
        fail()
    return value


@guarded
def pointer(value):
    closed(value, {'kind', 'path'})
    if value['kind'] not in {'owner', 'instruction', 'decision', 'check'}:
        fail()
    relative(value['path'])
    return value


def relative(value):
    safe_text(value, 512)
    if value.startswith('/') or '\\' in value or any(x in {'', '.', '..'} for x in value.split('/')):
        fail('unsafe_path', 3)
    return value


@guarded
def edge(value):
    closed(value, {'predicate', 'target', 'classification', 'pointer'})
    if value['predicate'] not in {'belongs_to', 'depends_on', 'related_to'}:
        fail()
    entity_id(value['target'])
    if value['classification'] not in {'declared', 'observed', 'inferred'}:
        fail()
    relative(value['pointer'])
    return value


@guarded
def record(value):
    closed(value, {'id', 'kind'}, FIELDS)
    entity_id(value['id'])
    if value['kind'] not in KINDS or not value['id'].startswith(value['kind']+':'):
        fail()
    for k, v in value.items():
        field(k, v)
    return value


def field(k, v):
    if k == 'title': safe_text(v, 128)
    elif k == 'description': safe_text(v, 512, True)
    elif k == 'aliases': strings(v)
    elif k == 'pointers':
        for p in seq(v, 100): pointer(p)
    elif k == 'edges':
        for e in seq(v, 100): edge(e)


@guarded
def config(value):
    closed(value, {'schema', 'roots', 'exclude_paths', 'exclude_identities', 'bounds'})
    if value['schema'] != 'ecosystem-index/config/v1': fail()
    closed(value['bounds'], {'roots', 'entities', 'input_bytes', 'snapshot_bytes', 'refresh_seconds'})
    for k, maximum in [('roots',500),('entities',5000),('input_bytes',INPUT_MAX),('snapshot_bytes',SNAPSHOT_MAX),('refresh_seconds',60)]:
        integer(value['bounds'][k], 1, maximum)
    roots = seq(value['roots'], value['bounds']['roots'])
    for p in seq(value['exclude_paths'], 500): absolute(p)
    for ident in seq(value['exclude_identities'], 500): safe_text(ident, 512)
    root_ids = set()
    for r in roots:
        closed(r, {'key', 'path', 'identity', 'scope', 'inventory', 'title', 'aliases', 'storage_fields', 'sources', 'git'})
        relative(r['key'])
        if '/' in r['key'] or len(r['key'])>128: fail()
        if r['key'] in root_ids: fail()
        root_ids.add(r['key'])
        absolute(r['path'])
        if r['scope'] not in {'permitted','unknown'}: fail()
        if r['inventory'] not in {'configured', 'native', 'workspace'}: fail()
        if r['identity'] is not None:
            closed(r['identity'], {'provider', 'remote'})
            if r['identity']['provider'] is not None: safe_text(r['identity']['provider'],256)
            if r['identity']['remote'] is not None: string(r['identity']['remote'],2048)
        safe_text(r['title'],128); strings(r['aliases'])
        if not set(strings(r['storage_fields'],5)) <= FIELDS: fail()
        source_paths=set()
        for s in seq(r['sources'],100):
            closed(s, {'path', 'adapter', 'kind', 'revision', 'fields'}, {'capability_scope'})
            relative(s['path'])
            if s['path']=='git' or s['path'] in source_paths: fail()
            source_paths.add(s['path'])
            if s['adapter'] not in {'json','yaml','capability-yaml','skill-frontmatter'}: fail()
            if s['adapter']=='skill-frontmatter':
                if s.get('capability_scope') not in {'global','project'}: fail()
            elif 'capability_scope' in s: fail()
            if s['kind'] not in {'capability','workspace','native'}: fail()
            if s['revision'] is not None: safe_text(s['revision'],128)
            if not set(strings(s['fields'],5)) <= set(r['storage_fields']): fail()
        g = r['git']
        if g is not None:
            closed(g, {'common_dir','git_dir'})
            absolute(g['common_dir']); absolute(g['git_dir'])
    return value


def absolute(value):
    string(value,4096)
    import os
    if not value.startswith('/') or os.path.normpath(value) != value:
        fail('unsafe_path',3)
    return value


@guarded
def metadata(value):
    closed(value, {'schema','entities'})
    if value['schema'] != 'ecosystem-index/metadata/v1': fail()
    ids=set()
    for item in seq(value['entities'],5000):
        record(item)
        if item['id'] in ids: fail()
        ids.add(item['id'])
        if item['kind'] not in {'capability','repository'}: fail()
    return value


@guarded
def observation(o):
    closed(o, {'field','value','classification','source_kind','pointer','revision','digest','observed_at','state'})
    if o['field'] not in FIELDS | {'identity','location'}: fail()
    if o['field'] in FIELDS: field(o['field'],o['value'])
    else: safe_text(o['value'],4096)
    if o['classification'] not in {'declared','observed','inferred'}: fail()
    if o['source_kind'] not in {'configured','native','workspace','capability','git'}: fail()
    relative(o['pointer'])
    if o['revision'] is not None: safe_text(o['revision'],128)
    string(o['digest'],64)
    if not re.fullmatch(r'[a-f0-9]{64}',o['digest']): fail()
    timestamp(o['observed_at'])
    if o['state'] not in {'current','stale','unverified','missing'}: fail()


@guarded
def snapshot(value):
    closed(value, {'schema','generation','observed_at','coverage','inputs','entities','reasons'})
    if value['schema'] != 'ecosystem-index/snapshot/v1': fail()
    integer(value['generation'],1,2**53)
    timestamp(value['observed_at'])
    if value['coverage'] not in {'complete','partial'}: fail()
    for reason in seq(value['reasons'],20):
        if reason not in REASONS: fail()
    input_keys=set()
    for item in seq(value['inputs'],50000):
        closed(item, {'key','digest','authorization_digest','state','records'})
        string(item['key'],1024)
        if item['key'] in input_keys: fail()
        input_keys.add(item['key'])
        string(item['digest'],64)
        if not re.fullmatch(r'[a-f0-9]{64}',item['digest']): fail()
        string(item['authorization_digest'],64)
        if not re.fullmatch(r'[a-f0-9]{64}',item['authorization_digest']): fail()
        if item['state'] not in {'current','stale','unverified','missing'}: fail()
        for r in seq(item['records'],5000): stored_entity(r)
    ids=set()
    for e in seq(value['entities'],5000):
        stored_entity(e)
        if e['id'] in ids: fail()
        ids.add(e['id'])
    return value


@guarded
def stored_entity(e):
    closed(e, {'id','kind','parent','observations','conflicts'})
    entity_id(e['id'])
    if e['kind'] not in KINDS or not e['id'].startswith(e['kind']+':'): fail()
    if e['parent'] is not None: entity_id(e['parent'])
    for o in seq(e['observations'],1000): observation(o)
    for f in seq(e['conflicts'],7):
        if f not in FIELDS | {'identity','location','parent'}: fail()


@guarded
def result(value):
    if type(value) is not dict: fail()
    if value.get('schema')!='ecosystem-index/result/v1': fail()
    if 'command' not in value:
        closed(value,{'schema','status','reasons'})
        if value['status'] not in {'invalid','unavailable','refused'}: fail()
    elif value['command']=='refresh':
        closed(value,{'schema','command','status','coverage','reasons','generation','snapshot_digest','counts'})
        if value['status'] not in {'complete','partial'} or value['coverage']!=value['status']: fail()
        integer(value['generation'],1,2**53)
        if not re.fullmatch(r'[a-f0-9]{64}',value['snapshot_digest']): fail()
        closed(value['counts'],{'entities','parsed','reused'})
        for k,v in value['counts'].items(): integer(v,0,5000 if k=='entities' else 50000)
    else:
        base={'schema','command','status','coverage','reasons','freshness'}
        command=value['command']
        extras={'search':{'candidates','truncated'},'describe':{'entity','locations'},
                'context':{'entity_id','source_owner','pointers','relationships','truncated'}}
        if command not in extras: fail()
        closed(value,base|extras[command])
        if value['status'] not in {'matches','ambiguous','none'} or value['coverage'] not in {'complete','partial'}: fail()
        f=value['freshness']; closed(f,{'observed_at','age_seconds','advisory_stale','advisory_after_seconds'})
        timestamp(f['observed_at'])
        if type(f['age_seconds']) not in {int,float} or f['age_seconds']<0: fail()
        if type(f['advisory_stale']) is not bool or f['advisory_after_seconds']!=86400: fail()
        if 'truncated' in value and type(value['truncated']) is not bool: fail()
        if command=='search':
            for c in seq(value['candidates'],20):
                closed(c,{'entity','score','contributions'}); stored_entity(c['entity']); integer(c['score'],1,100000)
                closed(c['contributions'],(),{'exact_id','title','aliases','description','identity'})
                for n in c['contributions'].values(): integer(n,1,100000)
        elif command=='describe':
            if value['entity'] is not None: stored_entity(value['entity'])
            for e in seq(value['locations'],5000): stored_entity(e)
        else:
            entity_id(value['entity_id'])
            if value['source_owner'] is not None: entity_id(value['source_owner'])
            for p in seq(value['pointers'],20):
                closed(p,{'entity_id','pointer','provenance'}); entity_id(p['entity_id']); pointer(p['pointer']); provenance(p['provenance'])
            for e in seq(value['relationships'],100):
                closed(e,{'source','edge','provenance'}); entity_id(e['source']); edge(e['edge']); provenance(e['provenance'])
    for r in seq(value['reasons'],20):
        if r not in REASONS: fail()
    return value


@guarded
def provenance(value):
    closed(value,{'classification','source_kind','pointer','revision','digest','observed_at','state'})
    observation({'field':'title','value':'Provenance',**value})
