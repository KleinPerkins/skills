#!/usr/bin/env python3
"""Pure v2 app-server planner/observer. Never starts a server or submits a turn.

No v1 ready plan or native-tool evidence is accepted or translated. Only shared
policy validation and semantic choice helpers are reused from the unchanged v1.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent

def sibling(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

c = sibling('app_server_contract')
v1 = sibling('native_dispatch')
VERSION = 'native-dispatch/v2'
RESULT_KEYS = ('schema status context request_sha256 source_sha256 evidence_sha256 pool_sha256 '
               'tier requested dispatch continuation pending worker acknowledged execution_matches_request '
               'reroutes used limit slot warnings limitations reason cleanup')
STATUSES = set('ready unavailable wait rejected submitted running succeeded failed terminated uncertain'.split())
TERMINAL = {'succeeded', 'failed', 'terminated'}
SOURCE_FILES = ('app_server_contract.py', 'app_server_dispatch.py', 'APP-SERVER-DISPATCH.md',
                'native_dispatch.py', 'native-model-bindings.json', 'model-tiers.json',
                'app-server-bindings.json')


def source_digest(policy, bindings, profiles):
    return c.digest(dict(namespace='app-server-dispatch-source/v2', policy=policy,
                         semantic_bindings=bindings, profiles=profiles,
                         files={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                                for p in SOURCE_FILES}))


def blank(reason=None):
    return dict(schema=VERSION, status='unavailable', context=None, request_sha256=None,
                source_sha256=None, evidence_sha256=None, pool_sha256=None, tier=None,
                requested=None, dispatch=None, continuation=None, pending=None, worker=None,
                acknowledged=None, execution_matches_request=None, reroutes=[], used=0,
                limit=None, slot=None, warnings=[], limitations=[], reason=reason,
                cleanup='not-started')


def refused(exc):
    # Never reflect arbitrary input, server errors, config or request bodies.
    return blank(str(exc) if isinstance(exc, c.Refusal) else 'invalid-schema')


def request_digest(request):
    stable = copy.deepcopy(request)
    stable['context'] = c.stable_context(stable['context'])
    return c.digest(stable)


def bound_sources(policy, bindings, profile):
    """Bind semantic policy to a separately source-qualified native surface."""
    v1.validate_sources(policy, bindings)
    c.require(set(profile['model_bindings']) == set(bindings['choices']), 'profile-mismatch')
    result = copy.deepcopy(bindings)
    for name, choice in result['choices'].items():
        choice['models']['codex'] = profile['model_bindings'][name]
    result['override_models']['codex'] = copy.deepcopy(profile['override_bindings'])
    v1.validate_sources(policy, result)
    return result


def evidence(row, ctx, expected_source, now):
    c.closed(row, 'schema context source_sha256 observed_at discovery_method origin pagination_complete include_hidden models')
    c.require(row['schema'] == 'native-offers/v2')
    c.context(row['context'])
    c.require(row['context'] == ctx, 'context-mismatch')
    c.sha(row['source_sha256'])
    c.require(row['source_sha256'] == expected_source, 'source-changed')
    c.require(row['discovery_method'] == 'model/list' and row['origin'] == 'qualified-native-interface', 'invalid-provenance')
    c.require(row['pagination_complete'] is True and row['include_hidden'] is False, 'incomplete-pagination')
    age = now - c.stamp(row['observed_at'])
    c.require(0 <= age <= v1.MAX_AGE_SECONDS, 'stale-evidence')
    normalized = c.models(row['models'])
    c.require(row['models'] == normalized, 'invalid-model-row')
    c.require(c.digest(normalized) == ctx['contract_sha256'], 'context-mismatch')


def classify(request, policy, bindings):
    c.closed(request, 'context operation_ref work_kind difficulty tier raise_reason mode selection override_authority_ref author_provider require_different_provider')
    c.context(request['context']); c.label(request['operation_ref'])
    c.enum(request['work_kind'], v1.KINDS); c.enum(request['difficulty'], {'normal', 'raised'})
    c.enum(request['mode'], {'auto', 'force', 'off'})
    c.require(type(request['require_different_provider']) is bool)
    tier, warnings = v1.KINDS[request['work_kind']], []
    if request['difficulty'] == 'raised':
        c.enum(request['tier'], v1.STRENGTH)
        c.require(v1.STRENGTH[request['tier']] > v1.STRENGTH[tier])
        c.label(request['raise_reason']); tier = request['tier']; warnings.append('raised')
    else:
        c.require(request['tier'] is None and request['raise_reason'] is None)
    author = request['author_provider']
    if request['work_kind'] in {'review', 'sign-off'}:
        c.label(author)
        providers = {r['provider'] for r in bindings['choices'].values()}
        providers.update(r['provider'] for r in bindings['override_models']['codex'])
        c.require(author in providers | {'none', 'unknown'})
    else:
        c.require(author is None and request['require_different_provider'] is False)
    if request['mode'] == 'force':
        c.choice(request['selection']); c.label(request['override_authority_ref'])
        choices = [v1.forced_choice(request['selection'], 'codex', bindings)]
        names = ['explicit-override']; warnings.append('explicit-override')
    else:
        c.require(request['selection'] is None and request['override_authority_ref'] is None)
        names = policy['tiers'][tier]['candidates']
        choices = [bindings['choices'][n] for n in names]
    c.require(request['mode'] != 'off', 'off')
    pairs = list(zip(names, choices))
    if author not in {None, 'none', 'unknown'}:
        pairs.sort(key=lambda item: item[1]['provider'] == author)
    return tier, warnings, author, pairs


def encode(choice, rows):
    model = choice['models']['codex']
    row = next((r for r in rows if r['model'] == model), None)
    if row is None: return None
    turn = {'model': model}
    if choice['effort'] is not None:
        if row['efforts'] is None or choice['effort'] not in row['efforts']: return None
        turn['effort'] = choice['effort']
    elif row['efforts'] is not None or row['fixed_behavior'] != choice['fixed_behavior']:
        return None
    return dict(thread_start={'model': model}, turn_start=turn)


def continuation(row):
    c.closed(row, 'schema request_sha256 source_sha256 stable_context_sha256 pool_sha256 previous_evidence_sha256 used limit next_slot retry_at refresh_required')
    c.require(row['schema'] == 'native-retry/v2')
    for key in ('request_sha256', 'source_sha256', 'stable_context_sha256', 'pool_sha256', 'previous_evidence_sha256'): c.sha(row[key])
    c.integer(row['used'], 0, 4); c.integer(row['limit'], 2, 4)
    c.require(row['limit'] in {2, 4} and row['used'] <= row['limit'])
    c.integer(row['next_slot'], 0, 1)
    c.require(type(row['refresh_required']) is bool)
    if row['retry_at'] is not None: c.stamp(row['retry_at'])
    c.require(row['used'] != row['limit'] // 2 or row['retry_at'] is not None)


def resolve(payload, policy, bindings, profiles, *, now=None):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    try:
        c.require(len(c.canonical(payload)) <= c.MAX_BYTES)
        c.closed(payload, 'schema request evidence continuation')
        c.require(payload['schema'] == 'native-dispatch-input/v2')
        req, ev = payload['request'], payload['evidence']
        c.require(type(req) is dict and 'context' in req)
        p = c.match_profile(req['context'], profiles)
        bound = bound_sources(policy, bindings, p)
        tier, warnings, author, pairs = classify(req, policy, bound)
        src = source_digest(policy, bindings, profiles)
        evidence(ev, req['context'], src, now)
        ideal = pairs[0][1]
        eligible = []
        for name, item in pairs:
            projection = encode(item, ev['models'])
            if projection is not None:
                eligible.append(dict(identity=name, choice=item, dispatch=projection))
        if req['require_different_provider']:
            c.require(author not in {None, 'unknown'}, 'no-eligible-choice')
            eligible = [e for e in eligible if e['choice']['provider'] != author]
        c.require(bool(eligible), 'override-unavailable' if req['mode'] == 'force' else 'no-eligible-choice')
        primary = eligible[0]
        secondary = next((e for e in eligible if e['choice']['provider'] != primary['choice']['provider']), None)
        pool = [primary] + ([secondary] if secondary else [])
        pool_hash = c.digest(pool)
        used, limit, slot, retry_at = 0, len(pool) * 2, 0, None
        cont = payload['continuation']
        if cont is not None:
            continuation(cont)
            c.require(cont['request_sha256'] == request_digest(req) and cont['source_sha256'] == src
                      and cont['stable_context_sha256'] == c.digest(c.stable_context(req['context'])), 'context-mismatch')
            used, limit, retry_at = cont['used'], cont['limit'], cont['retry_at']
            if cont['pool_sha256'] == pool_hash: slot = cont['next_slot'] % len(pool)
            if cont['refresh_required']:
                c.require(cont['previous_evidence_sha256'] != c.digest(ev), 'stale-evidence')
        c.require(used < limit, 'retry-exhausted')
        result = blank()
        result.update(context=copy.deepcopy(req['context']), request_sha256=request_digest(req),
                      source_sha256=src, evidence_sha256=c.digest(ev), pool_sha256=pool_hash,
                      tier=tier, used=used, limit=limit, slot=slot, warnings=warnings,
                      limitations=['execution-identity-unverified', 'native-rejection-unobserved', 'native-failure-unobserved'])
        if retry_at is not None and now < c.stamp(retry_at):
            result.update(status='wait', reason='retry-wait', continuation=copy.deepcopy(cont))
            return result
        selected = pool[slot]
        item = selected['choice']
        if v1.choice_key(item) != v1.choice_key(ideal): warnings.append('fallback')
        family_first = next((choice for _, choice in pairs if v1.choice_key(choice) == v1.choice_key(item)), item)
        if item != family_first: warnings.append('step-down')
        if author == item['provider']: warnings.append('same-provider-review')
        if author == 'unknown': warnings.append('review-provider-unverified')
        result.update(status='ready', dispatch=copy.deepcopy(selected['dispatch']),
                      requested={k: item[k] for k in ('provider', 'family', 'effort', 'fixed_behavior')})
        return result
    except (c.Refusal, v1.Unavailable, ValueError, TypeError, KeyError, RecursionError):
        return refused(sys.exc_info()[1])


def projection(row, requested):
    c.closed(row, 'thread_start turn_start')
    c.closed(row['thread_start'], 'model')
    c.closed(row['turn_start'], 'model effort' if requested['effort'] is not None else 'model')
    c.label(row['thread_start']['model'])
    c.require(row['thread_start']['model'] == row['turn_start']['model'])
    if requested['effort'] is not None: c.require(row['turn_start']['effort'] == requested['effort'])


def identity_match(row):
    """Derive matching solely from validated acknowledgement and reroute history."""
    model = row['dispatch']['thread_start']['model']
    if any(r['from_model'] != model or r['to_model'] != model for r in row['reroutes']):
        return False
    ack = row['acknowledged']
    if ack is None:
        return None
    expected = dict(row['requested'], model=model)
    if any(ack[k] is not None and ack[k] != value for k, value in expected.items()):
        return False
    return True if all(ack[k] == value for k, value in expected.items()) else None


def validate_result(row, policy, bindings, profiles):
    c.closed(row, RESULT_KEYS); c.require(row['schema'] == VERSION)
    c.enum(row['status'], {'ready', 'submitted', 'running', 'rejected', 'uncertain'} | TERMINAL)
    c.enum(row['cleanup'], {'not-started', 'pending', 'confirmed', 'unknown'})
    c.require(type(row['warnings']) is list and type(row['limitations']) is list and type(row['reroutes']) is list)
    for code in row['warnings']: c.enum(code, c.WARNINGS)
    for code in row['limitations']: c.enum(code, c.LIMITATIONS)
    if row['reason'] is not None: c.enum(row['reason'], c.REASONS)
    c.require(row['execution_matches_request'] is None or type(row['execution_matches_request']) is bool)
    c.integer(row['used'], 0, 4); c.integer(row['limit'], 2, 4)
    c.require(row['limit'] in {2, 4} and row['used'] < row['limit'])
    c.integer(row['slot'], 0, 1); c.enum(row['tier'], v1.STRENGTH)
    for key in ('request_sha256', 'source_sha256', 'evidence_sha256', 'pool_sha256'): c.sha(row[key])
    c.require(row['source_sha256'] == source_digest(policy, bindings, profiles), 'source-changed')
    p = c.match_profile(row['context'], profiles)
    bound = bound_sources(policy, bindings, p)
    c.choice(row['requested']); projection(row['dispatch'], row['requested'])
    # Check the semantic/native binding again; a forged projection cannot be observed.
    selected = v1.forced_choice(row['requested'], 'codex', bound)
    c.require(selected['models']['codex'] == row['dispatch']['thread_start']['model'], 'profile-mismatch')
    c.ack(row['acknowledged'], p)
    if row['pending'] is not None:
        c.pending(row['pending'])
        c.require(row['pending']['server_instance_ref'] == row['context']['server_instance_ref'], 'context-mismatch')
    if row['worker'] is not None:
        c.worker(row['worker'])
        c.require(row['worker']['server_instance_ref'] == row['context']['server_instance_ref'], 'context-mismatch')
        c.require(row['pending'] is not None and row['worker']['thread_id'] == row['pending']['thread_id'], 'context-mismatch')
    c.require(len(row['reroutes']) <= 64 and len({c.digest(r) for r in row['reroutes']}) == len(row['reroutes']))
    for event in row['reroutes']:
        c.reroute(event); c.require(event['worker'] == row['worker'], 'context-mismatch')
    match = identity_match(row)
    c.require(row['execution_matches_request'] is match, 'invalid-provenance')
    c.require(('execution-identity-unverified' in row['limitations']) == (match is not True), 'invalid-provenance')
    if row['continuation'] is not None: continuation(row['continuation'])
    if row['status'] == 'ready':
        c.require(row['pending'] is None and row['worker'] is None and row['cleanup'] == 'not-started'
                  and row['acknowledged'] is None and not row['reroutes'] and row['execution_matches_request'] is None)
    status = row['status']
    if status in {'ready', 'submitted', 'rejected'}:
        c.require(row['worker'] is None and row['acknowledged'] is None
                  and row['execution_matches_request'] is None and not row['reroutes'])
    if status == 'ready':
        c.require(row['continuation'] is None and row['reason'] is None)
    if status == 'submitted':
        c.require(row['pending'] is not None and row['cleanup'] == 'pending'
                  and row['continuation'] is None and row['reason'] is None)
    if status in TERMINAL | {'running'}:
        c.require(row['worker'] is not None and row['continuation'] is None)
        c.require(row['cleanup'] in ({'pending'} if status == 'running' else {'pending', 'confirmed', 'unknown'}))
    if status == 'uncertain':
        c.require(row['pending'] is not None and row['continuation'] is None
                  and row['cleanup'] in {'unknown', 'confirmed'} and row['reason'] == 'acceptance-unknown')
    if status == 'rejected':
        c.require(row['reason'] == 'prelaunch-rejection')
        if row['pending'] is None: c.require(row['cleanup'] == 'not-started')
        else: c.require(row['cleanup'] in {'pending', 'confirmed', 'unknown'})
        cont = row['continuation']
        eligible = row['cleanup'] in {'not-started', 'confirmed'}
        c.require((cont is not None) == eligible)
        if cont is not None:
            c.require(cont['request_sha256'] == row['request_sha256']
                      and cont['source_sha256'] == row['source_sha256']
                      and cont['stable_context_sha256'] == c.digest(c.stable_context(row['context']))
                      and cont['pool_sha256'] == row['pool_sha256']
                      and cont['previous_evidence_sha256'] == row['evidence_sha256']
                      and cont['used'] == row['used'] + 1 and cont['limit'] == row['limit']
                      and cont['next_slot'] == (row['slot'] + 1) % (row['limit'] // 2))
            c.require(not cont['refresh_required'] or row['pending'] is None)
    return p, bound


def apply_ack(row, ack, profile):
    c.ack(ack, profile)
    if ack is None: return
    previous = row['acknowledged']
    if previous is not None:
        # Later native acknowledgements can fill unknowns, not erase contradictions.
        for key in ('provider', 'family', 'model', 'effort', 'fixed_behavior'):
            c.require(previous[key] is None or ack[key] is None or previous[key] == ack[key], 'invalid-provenance')
        ack = {k: (ack[k] if ack[k] is not None else previous[k]) for k in ack}
    row['acknowledged'] = copy.deepcopy(ack)
    expected = dict(row['requested'], model=row['dispatch']['thread_start']['model'])
    mismatch = any(ack[k] is not None and ack[k] != v for k, v in expected.items())
    if mismatch or row['execution_matches_request'] is False:
        row['execution_matches_request'] = False
    elif all(ack[k] == v for k, v in expected.items()):
        row['execution_matches_request'] = True
        row['limitations'] = [x for x in row['limitations'] if x != 'execution-identity-unverified']


def retry_record(row, now, refresh=False):
    used = row['used'] + 1
    return dict(schema='native-retry/v2', request_sha256=row['request_sha256'], source_sha256=row['source_sha256'],
                stable_context_sha256=c.digest(c.stable_context(row['context'])), pool_sha256=row['pool_sha256'],
                previous_evidence_sha256=row['evidence_sha256'], used=used, limit=row['limit'],
                next_slot=(row['slot'] + 1) % (row['limit'] // 2),
                retry_at=c.iso(now + v1.WAIT_SECONDS) if used == row['limit'] // 2 else None,
                refresh_required=refresh)


def observe(payload, policy, bindings, profiles, *, now=None):
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    try:
        c.require(len(c.canonical(payload)) <= c.MAX_BYTES)
        c.closed(payload, 'schema prior event'); c.require(payload['schema'] == 'native-observation-input/v2')
        row = copy.deepcopy(payload['prior']); event = payload['event']
        p, bound = validate_result(row, policy, bindings, profiles)
        c.require(type(event) is dict and type(event.get('kind')) is str)
        kind, status = event['kind'], row['status']
        if kind == 'submitted':
            c.closed(event, 'kind pending effective_provider'); c.pending(event['pending'])
            c.label(event['effective_provider'])
            c.require(event['effective_provider'] == p['launch_descriptor']['provider_id'], 'profile-mismatch')
            c.require(status in {'ready', 'submitted'})
            c.require(event['pending']['server_instance_ref'] == row['context']['server_instance_ref'], 'context-mismatch')
            if status == 'submitted': c.require(row['pending'] == event['pending'], 'context-mismatch')
            row.update(status='submitted', pending=copy.deepcopy(event['pending']), cleanup='pending', continuation=None)
        elif kind == 'started' or kind in TERMINAL:
            c.closed(event, 'kind worker request_id acknowledged'); c.worker(event['worker'])
            c.require(status in {'submitted', 'running'} | TERMINAL)
            c.require(row['pending'] is not None and event['request_id'] == row['pending']['request_id'], 'context-mismatch')
            c.require(event['worker']['server_instance_ref'] == row['pending']['server_instance_ref']
                      and event['worker']['thread_id'] == row['pending']['thread_id'], 'context-mismatch')
            if row['worker'] is not None: c.require(row['worker'] == event['worker'], 'context-mismatch')
            if status in TERMINAL:
                # Duplicate or delayed start is idempotent; contradictory terminals fail closed.
                c.require(kind == status or kind == 'started', 'acceptance-unknown')
            else:
                row['status'] = 'running' if kind == 'started' else kind
            row['worker'] = copy.deepcopy(event['worker']); row['continuation'] = None
            apply_ack(row, event['acknowledged'], p)
            if kind in {'failed', 'terminated'}: row['reason'] = 'post-start-failure'
        elif kind in {'prelaunch-rejected', 'not-offered'}:
            c.closed(event, 'kind signal_code')
            c.require(status in {'ready', 'submitted'} and row['worker'] is None, 'post-start-failure')
            if kind == 'prelaunch-rejected':
                c.label(event['signal_code'])
                c.require(event['signal_code'] in p['prelaunch_codes'], 'invalid-provenance')
            else:
                # A changed discovery list only proves unavailability BEFORE submission.
                c.require(status == 'ready' and event['signal_code'] is None, 'acceptance-unknown')
            row.update(status='rejected', reason='prelaunch-rejection', continuation=retry_record(row, now, kind == 'not-offered'))
        elif kind == 'invalid-request':
            c.closed(event, 'kind')
            c.require(status == 'ready', 'acceptance-unknown')
            # Caller composition repair must not execute or consume/reset a slot.
            repair = retry_record(row, now)
            repair.update(used=row['used'], next_slot=row['slot'],
                          retry_at=c.iso(now) if row['used'] == row['limit'] // 2 else None)
            row.update(status='unavailable', reason='invalid-request', dispatch=None, continuation=repair)
        elif kind == 'acceptance-unknown':
            c.closed(event, 'kind'); c.require(status in {'submitted', 'running', 'uncertain'})
            row.update(status='uncertain', reason='acceptance-unknown', continuation=None, cleanup='unknown')
        elif kind == 'rerouted':
            c.closed(event, 'kind reroute'); c.reroute(event['reroute'])
            c.require(status in {'running'} | TERMINAL and event['reroute']['worker'] == row['worker'], 'context-mismatch')
            r = event['reroute']
            if r not in row['reroutes']:
                c.require(len(row['reroutes']) < 64)
                row['reroutes'].append(copy.deepcopy(r))
            requested = row['dispatch']['thread_start']['model']
            if r['to_model'] != requested or r['from_model'] != requested:
                row.update(execution_matches_request=False, reason='native-reroute', continuation=None)
                if 'rerouted' not in row['limitations']: row['limitations'].append('rerouted')
                known = {b['models']['codex'] for b in bound['choices'].values()}
                known.update(b['model'] for b in bound['override_models']['codex'])
                if r['to_model'] not in known and 'reroute-target-unmapped' not in row['limitations']:
                    row['limitations'].append('reroute-target-unmapped')
                # An earlier requested-model acknowledgement no longer identifies the
                # entire execution. Do not fabricate an acknowledgement from reroute.
                if 'execution-identity-unverified' not in row['limitations']:
                    row['limitations'].append('execution-identity-unverified')
        elif kind in {'cleanup-confirmed', 'cleanup-unknown'}:
            c.closed(event, 'kind')
            c.require(status in TERMINAL | {'rejected', 'uncertain'})
            c.require(row['pending'] is not None)  # No model custody exists before submission.
            row['cleanup'] = 'confirmed' if kind == 'cleanup-confirmed' else 'unknown'
            if kind == 'cleanup-confirmed' and status == 'rejected' and row['continuation'] is None:
                row['continuation'] = retry_record(row, now)
            if kind == 'cleanup-unknown':
                row['continuation'] = None
                if 'cleanup-unverified' not in row['limitations']: row['limitations'].append('cleanup-unverified')
        else:
            raise c.Refusal()
        # A rejected submitted call cannot produce another attempt until cleanup
        # is positively established. Unknown cleanup never grants continuation.
        if row['status'] == 'rejected' and row['cleanup'] not in {'not-started', 'confirmed'}:
            row['continuation'] = None
        return row
    except (c.Refusal, v1.Unavailable, ValueError, TypeError, KeyError, RecursionError):
        # Return a non-executable refusal; caller must retain original custody and
        # stop/clean any pending worker. A malformed event is never prelaunch proof.
        return refused(sys.exc_info()[1])


def sources():
    return (c.load(ROOT / 'model-tiers.json'), c.load(ROOT / 'native-model-bindings.json'),
            c.load(ROOT / 'app-server-bindings.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('source-digest', 'plan', 'observe'))
    parser.add_argument('--input')
    args = parser.parse_args()
    try:
        policy, bindings, profiles = sources()
        if args.operation == 'source-digest':
            result = {'source_sha256': source_digest(policy, bindings, profiles)}
        else:
            payload = c.load(args.input)
            result = (resolve if args.operation == 'plan' else observe)(payload, policy, bindings, profiles)
    except (c.Refusal, OSError, TypeError, ValueError, RecursionError):
        result = refused(sys.exc_info()[1])
    print(c.canonical(result).decode('utf-8'))
    return 0 if result.get('status') != 'unavailable' else 2


if __name__ == '__main__':
    raise SystemExit(main())
