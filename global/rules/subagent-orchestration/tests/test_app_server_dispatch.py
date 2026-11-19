"""MOD-01/02 fixtures only: no server, native offers, entitlement or execution proof."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_native_dispatch import sources

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('app_server_dispatch', ROOT / 'app_server_dispatch.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
c = a.c
NOW = datetime(2026, 10, 31, 20, tzinfo=timezone.utc).timestamp()


class AppServerTests(unittest.TestCase):
    def setUp(self):
        self.policy, self.bindings = sources()
        self.profile = dict(schema='app-server-host-profile/v1', profile_id='fixture-only',
                            host_build='fixture-build', server_binary_sha256='a' * 64,
                            protocol_schema_sha256='b' * 64, initialize_profile_sha256='c' * 64,
                            launch_descriptor=dict(schema='app-server-provider-profile/v1',
                                profile_id='fixture-only', provider_id='fixture-provider', transport='stdio',
                                source_revision='fixture-source', offer_semantics='qualified-native-offers'),
                            model_bindings={k: v['models']['codex'] for k, v in self.bindings['choices'].items()},
                            override_bindings=[], acknowledgement_methods=['fixture-ack'],
                            prelaunch_codes=['fixture-proven-no-start'])
        self.profiles = dict(schema='app-server-bindings/v1', profiles=[self.profile])
        models = c.models([dict(model=m, efforts=e, fixed_behavior=b) for m, e, b in (
            ('opaque-17', ['high', 'max'], None), ('opaque-low', ['max'], None),
            ('token.max', ['high'], None), ('opaque/42', None, 'fast'))])
        self.ctx = dict(host='codex', surface=c.SURFACE, session_id='fixture-session',
                        host_build='fixture-build', server_binary_sha256='a' * 64,
                        protocol_schema_sha256='b' * 64, server_instance_ref='fixture-instance',
                        contract_sha256=c.digest(models),
                        launch_or_provider_profile_sha256=c.digest(self.profile['launch_descriptor']),
                        initialize_profile_sha256='c' * 64)
        self.ev = dict(schema='native-offers/v2', context=copy.deepcopy(self.ctx),
                       source_sha256=a.source_digest(self.policy, self.bindings, self.profiles),
                       observed_at=c.iso(NOW), discovery_method='model/list', origin='qualified-native-interface',
                       pagination_complete=True, include_hidden=False, models=models)
        self.req = dict(context=self.ctx, operation_ref='fixture-op', work_kind='design', difficulty='normal',
                        tier=None, raise_reason=None, mode='auto', selection=None, override_authority_ref=None,
                        author_provider=None, require_different_provider=False)
        self.pending = dict(server_instance_ref='fixture-instance', thread_id='thread-1', request_id='rpc-1')
        self.worker = dict(server_instance_ref='fixture-instance', thread_id='thread-1', turn_id='turn-1')

    def plan(self, continuation=None, now=NOW):
        return a.resolve(dict(schema='native-dispatch-input/v2', request=self.req, evidence=self.ev,
                              continuation=continuation), self.policy, self.bindings, self.profiles, now=now)

    def obs(self, prior, kind, now=NOW, **data):
        return a.observe(dict(schema='native-observation-input/v2', prior=prior, event=dict(kind=kind, **data)),
                         self.policy, self.bindings, self.profiles, now=now)

    def sync_source(self):
        self.ev['source_sha256'] = a.source_digest(self.policy, self.bindings, self.profiles)

    def offers(self, rows):
        self.ev['models'] = c.models(rows)
        self.ctx['contract_sha256'] = c.digest(self.ev['models'])
        self.ev['context'] = copy.deepcopy(self.ctx)

    def refuse(self, result, reason=None):
        self.assertEqual(result['status'], 'unavailable', result)
        self.assertIsNone(result['dispatch'])
        if reason: self.assertEqual(result['reason'], reason)

    def submitted(self, prior=None):
        return self.obs(prior or self.plan(), 'submitted', pending=self.pending, effective_provider='fixture-provider')

    def started(self, prior=None, ack=None):
        return self.obs(prior or self.submitted(), 'started', worker=self.worker, request_id='rpc-1', acknowledged=ack)

    def terminal(self, prior=None, kind='succeeded', ack=None):
        return self.obs(prior or self.started(), kind, worker=self.worker, request_id='rpc-1', acknowledged=ack)

    def native_ack(self, prior, **changes):
        result = dict(prior['requested'], model=prior['dispatch']['thread_start']['model'],
                      origin='native-execution', evidence_method='fixture-ack')
        result.update(changes)
        return result

    def test_separate_surface_projection_and_identity(self):
        result = self.plan()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['dispatch'], dict(thread_start={'model': 'opaque-17'},
                                                turn_start={'model': 'opaque-17', 'effort': 'max'}))
        self.assertIsNone(result['acknowledged'])
        self.assertEqual(result['schema'], 'native-dispatch/v2')
        self.assertNotIn('ephemeral', result['dispatch']['thread_start'])
        self.assertNotIn('reasoning_effort', result['dispatch']['turn_start'])

    def test_fixed_behavior_omits_effort(self):
        self.req['work_kind'] = 'run'
        result = self.plan()
        self.assertEqual(result['requested']['fixed_behavior'], 'fast')
        self.assertEqual(result['dispatch']['turn_start'], {'model': 'opaque/42'})

    def test_full_work_kind_and_raised_tier_semantics(self):
        for kind, tier in a.v1.KINDS.items():
            with self.subTest(kind=kind):
                self.req.update(work_kind=kind, author_provider='none' if kind in {'review', 'sign-off'} else None)
                self.assertEqual(self.plan()['tier'], tier)
        self.req.update(work_kind='build', author_provider=None, difficulty='raised', tier='deep', raise_reason='cross-surface architecture')
        self.assertIn('raised', self.plan()['warnings'])
        self.req['tier'] = 'economy'
        self.refuse(self.plan())

    def test_non_review_fields_and_unknown_author_refused(self):
        for author, different in [('alpha', False), (None, True), ('unknown', False)]:
            self.req.update(author_provider=author, require_different_provider=different)
            self.refuse(self.plan())
        self.req.update(work_kind='review', author_provider=None, require_different_provider=False)
        self.refuse(self.plan())
        self.req['author_provider'] = 'arbitrary-provider'
        self.refuse(self.plan())

    def test_review_partition_and_warnings(self):
        self.req.update(work_kind='review', author_provider='alpha')
        self.assertEqual(self.plan()['requested']['provider'], 'beta')
        self.req['author_provider'] = 'unknown'
        self.assertIn('review-provider-unverified', self.plan()['warnings'])
        self.req['require_different_provider'] = True
        self.refuse(self.plan(), 'no-eligible-choice')
        self.req.update(author_provider='alpha', require_different_provider=False)
        self.offers([r for r in self.ev['models'] if r['model'] == 'token.max'])
        self.assertIn('same-provider-review', self.plan()['warnings'])

    def test_force_requires_authority_and_no_fallback(self):
        self.req.update(mode='force', selection=dict(provider='alpha', family='large', effort='high', fixed_behavior=None))
        self.refuse(self.plan())
        self.req['override_authority_ref'] = 'fixture-explicit-operation-authority'
        result = self.plan()
        self.assertEqual(result['dispatch']['turn_start']['effort'], 'high')
        self.assertIn('explicit-override', result['warnings'])
        self.req['selection']['effort'] = 'ultra'
        self.refuse(self.plan(), 'override-unavailable')
        self.req.update(mode='auto', selection=None)
        self.refuse(self.plan())

    def test_off_never_dispatches(self):
        self.req['mode'] = 'off'
        self.refuse(self.plan(), 'off')

    def test_catalog_only_unknown_api_and_native_v1_evidence_refused(self):
        for origin in ['catalog-only', 'account-api', 'unknown', 'native-tool']:
            self.ev['origin'] = origin
            self.refuse(self.plan(), 'invalid-provenance')
        self.ev['origin'] = 'qualified-native-interface'
        self.ev['schema'] = 'native-offers/v1'
        self.refuse(self.plan())

    def test_profiles_require_exact_binary_schema_build_launch_and_handshake(self):
        for key in ['server_binary_sha256', 'protocol_schema_sha256', 'initialize_profile_sha256',
                    'launch_or_provider_profile_sha256', 'host_build']:
            with self.subTest(key=key):
                old = self.ctx[key]; self.ctx[key] = 'd' * 64
                self.refuse(self.plan(), 'profile-mismatch')
                self.ctx[key] = old
        for semantics in ['catalog-only', 'unknown']:
            self.profile['launch_descriptor']['offer_semantics'] = semantics
            self.ctx['launch_or_provider_profile_sha256'] = c.digest(self.profile['launch_descriptor'])
            self.refuse(self.plan(), 'invalid-provenance')

    def test_no_existing_surface_alias_or_unknown_host(self):
        for surface in ['local-macos-desktop', 'cli', 'cloud', 'fixture', 'remote']:
            self.ctx['surface'] = surface
            self.refuse(self.plan(), 'unsupported-surface')

    def test_missing_profile_never_reuses_desktop_model_bindings(self):
        self.profiles['profiles'] = []
        self.refuse(self.plan(), 'profile-mismatch')

    def test_explicit_mapping_required_even_with_native_offer(self):
        for name in self.profile['model_bindings']: self.profile['model_bindings'][name] = None
        self.sync_source()
        self.refuse(self.plan(), 'no-eligible-choice')

    def test_inconsistent_semantic_native_binding_refused(self):
        self.profile['model_bindings']['beta-pro-2-max'] = 'opaque-17'
        self.sync_source()
        self.refuse(self.plan())

    def test_pagination_hidden_freshness_source_and_context_refusals(self):
        for field, value, reason in [('pagination_complete', False, 'incomplete-pagination'),
                                     ('include_hidden', True, 'incomplete-pagination'),
                                     ('source_sha256', '0' * 64, 'source-changed'),
                                     ('discovery_method', 'account/models', 'invalid-provenance')]:
            with self.subTest(field=field):
                old = self.ev[field]; self.ev[field] = value
                self.refuse(self.plan(), reason); self.ev[field] = old
        self.assertEqual(self.plan(now=NOW + 900)['status'], 'ready')
        self.refuse(self.plan(now=NOW + 901), 'stale-evidence')
        self.refuse(self.plan(now=NOW - 1), 'stale-evidence')
        self.ev['context']['server_instance_ref'] = 'restarted-instance'
        self.refuse(self.plan(), 'context-mismatch')

    def test_normalization_duplicates_unknown_efforts_and_no_inherit(self):
        rows = list(reversed(self.ev['models']))
        self.assertEqual(c.models(rows), self.ev['models'])
        for rows in [self.ev['models'] * 2, [dict(model='inherit', efforts=['high'], fixed_behavior=None)],
                     [dict(model='x', efforts=['high', 'high'], fixed_behavior=None)],
                     [dict(model='x', efforts=['unspecified'], fixed_behavior=None)],
                     [dict(model='x', efforts=None, fixed_behavior=None)]]:
            with self.assertRaises(c.Refusal): c.models(rows)
        self.ev['models'].reverse()
        self.refuse(self.plan(), 'invalid-model-row')

    def test_low_effort_fallback_follows_catalog_not_max_default(self):
        self.offers([dict(model='opaque-17', efforts=['high'], fixed_behavior=None)])
        result = self.plan()
        self.assertEqual(result['requested']['effort'], 'high')
        self.assertIn('step-down', result['warnings'])

    def test_bounded_primary_secondary_wait_exhaustion(self):
        plan = self.plan()
        providers = []
        now = NOW
        for attempt in range(4):
            providers.append(plan['requested']['provider'])
            reject = self.obs(plan, 'prelaunch-rejected', signal_code='fixture-proven-no-start', now=now)
            self.assertEqual(reject['status'], 'rejected')
            cont = reject['continuation']
            if attempt == 1:
                waiting = self.plan(cont, now=now)
                self.assertEqual(waiting['status'], 'wait'); self.assertIsNone(waiting['dispatch'])
                now += 60
            plan = self.plan(cont, now=now)
        self.assertEqual(providers, ['alpha', 'beta', 'alpha', 'beta'])
        self.refuse(plan, 'retry-exhausted')

    def test_one_provider_limit_and_wait(self):
        self.offers([dict(model='opaque-17', efforts=['max'], fixed_behavior=None)])
        first = self.plan(); self.assertEqual(first['limit'], 2)
        rejected = self.obs(first, 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        self.assertEqual(self.plan(rejected['continuation'])['status'], 'wait')
        second = self.plan(rejected['continuation'], now=NOW + 60)
        final = self.obs(second, 'prelaunch-rejected', signal_code='fixture-proven-no-start', now=NOW + 60)
        self.refuse(self.plan(final['continuation'], now=NOW + 60), 'retry-exhausted')

    def test_refresh_does_not_reset_retry_budget_or_instance(self):
        rejected = self.obs(self.plan(), 'not-offered', signal_code=None)
        self.refuse(self.plan(rejected['continuation']), 'stale-evidence')
        self.ev['observed_at'] = c.iso(NOW + 1)
        result = self.plan(rejected['continuation'], now=NOW + 1)
        self.assertEqual(result['used'], 1)
        self.ctx['server_instance_ref'] = 'new-instance'; self.ev['context'] = copy.deepcopy(self.ctx)
        self.refuse(self.plan(rejected['continuation'], now=NOW + 1), 'context-mismatch')

    def test_invalid_request_repairs_same_slot_without_budget_reset(self):
        rejected = self.obs(self.plan(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        second = self.plan(rejected['continuation'])
        invalid = self.obs(second, 'invalid-request')
        self.refuse(invalid, 'invalid-request')
        repaired = self.plan(invalid['continuation'])
        self.assertEqual((repaired['used'], repaired['slot'], repaired['requested']),
                         (second['used'], second['slot'], second['requested']))
        self.refuse(self.obs(self.submitted(), 'invalid-request'), 'acceptance-unknown')

    def test_unknown_rejection_auth_rate_limit_never_fallback(self):
        for signal in ['401', '429', 'timeout', 'disconnect', 'model-not-found']:
            self.refuse(self.obs(self.plan(), 'prelaunch-rejected', signal_code=signal), 'invalid-provenance')
        self.refuse(self.obs(self.submitted(), 'not-offered', signal_code=None), 'acceptance-unknown')

    def test_submitted_prelaunch_rejection_withholds_retry_until_cleanup(self):
        rejected = self.obs(self.submitted(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        self.assertIsNone(rejected['continuation'])
        unknown = self.obs(rejected, 'cleanup-unknown')
        self.assertIsNone(unknown['continuation'])
        cleaned = self.obs(rejected, 'cleanup-confirmed')
        self.assertEqual(cleaned['continuation']['used'], 1)

    def test_effective_native_provider_must_match_before_turn_submission(self):
        for provider in ['other-provider', None, '']:
            result = self.obs(self.plan(), 'submitted', pending=self.pending, effective_provider=provider)
            self.refuse(result)
        self.assertEqual(self.submitted()['status'], 'submitted')
        self.assertIsNone(self.submitted()['acknowledged'])

    def test_cleanup_events_preserve_closed_state_and_idempotence(self):
        ready_rejection = self.obs(self.plan(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        submitted_rejection = self.obs(self.submitted(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        for kind in ['cleanup-confirmed', 'cleanup-unknown']:
            self.refuse(self.obs(ready_rejection, kind))
            first = self.obs(submitted_rejection, kind)
            self.assertEqual(first['status'], 'rejected')
            self.assertEqual(self.obs(first, kind), first)

    def test_lifecycle_and_requested_not_acknowledged(self):
        ready = self.plan(); submitted = self.submitted(ready); running = self.started(submitted)
        self.assertEqual(submitted['status'], 'submitted')
        self.assertEqual(running['status'], 'running')
        result = self.terminal(running)
        self.assertEqual(result['status'], 'succeeded')
        self.assertIsNone(result['acknowledged']); self.assertIsNone(result['execution_matches_request'])
        self.assertEqual(result['cleanup'], 'pending')
        result = self.obs(result, 'cleanup-confirmed')
        self.assertEqual(result['cleanup'], 'confirmed')
        self.assertIsNone(result['continuation'])

    def test_ambiguous_acceptance_and_post_start_failure_never_retry(self):
        unknown = self.obs(self.submitted(), 'acceptance-unknown')
        self.assertEqual(unknown['status'], 'uncertain'); self.assertIsNone(unknown['continuation'])
        cleaned = self.obs(unknown, 'cleanup-confirmed')
        self.assertEqual(cleaned['status'], 'uncertain'); self.assertIsNone(cleaned['continuation'])
        for prior in [unknown, self.started(), self.terminal(kind='failed')]:
            self.refuse(self.obs(prior, 'prelaunch-rejected', signal_code='fixture-proven-no-start'), 'post-start-failure')

    def test_out_of_order_terminal_and_duplicate_events(self):
        result = self.terminal(self.submitted())
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(self.terminal(result), result)
        self.assertEqual(self.started(result), result)
        self.refuse(self.terminal(result, kind='failed'), 'acceptance-unknown')

    def test_foreign_worker_or_request_ids_never_attach(self):
        for field, value in [('server_instance_ref', 'other'), ('thread_id', 'other'), ('turn_id', 'other')]:
            worker = dict(self.worker, **{field: value})
            self.refuse(self.obs(self.started(), 'succeeded', worker=worker, request_id='rpc-1', acknowledged=None), 'context-mismatch')
        self.refuse(self.obs(self.submitted(), 'started', worker=self.worker, request_id='foreign-rpc', acknowledged=None), 'context-mismatch')

    def test_native_ack_only_partial_unknown_and_conflicts(self):
        submitted = self.submitted()
        ack = self.native_ack(submitted)
        for origin in ['requested', 'configuration', 'model-self-report']:
            self.refuse(self.started(submitted, dict(ack, origin=origin)))
        self.refuse(self.started(submitted, dict(ack, evidence_method='unqualified-ack')), 'invalid-provenance')
        partial = self.started(submitted, dict(ack, effort=None))
        self.assertIsNone(partial['execution_matches_request'])
        full = self.terminal(partial, ack=ack)
        self.assertTrue(full['execution_matches_request'])
        self.assertNotIn('execution-identity-unverified', full['limitations'])
        self.refuse(self.terminal(full, ack=dict(ack, effort='high')), 'invalid-provenance')

    def test_reroute_stays_mismatch_even_if_switches_back(self):
        running = self.started()
        event = dict(worker=self.worker, from_model='opaque-17', to_model='unmapped-native-target',
                     reason_class='unknown', reason_code=None)
        result = self.obs(running, 'rerouted', reroute=event)
        self.assertFalse(result['execution_matches_request'])
        self.assertIn('reroute-target-unmapped', result['limitations'])
        self.assertIsNone(result['acknowledged'])
        self.assertEqual(self.obs(result, 'rerouted', reroute=event), result)
        back = dict(event, from_model=event['to_model'], to_model=event['from_model'])
        result = self.obs(result, 'rerouted', reroute=back)
        result = self.terminal(result, ack=self.native_ack(running))
        self.assertFalse(result['execution_matches_request'])
        self.assertEqual(len(result['reroutes']), 2)
        event['reason_code'] = 'raw-sensitive-server-message'
        self.refuse(self.obs(running, 'rerouted', reroute=event))

    def test_reroute_before_start_response_requires_correlated_terminal_or_start(self):
        event = dict(worker=self.worker, from_model='opaque-17', to_model='opaque-low', reason_class='unknown', reason_code=None)
        self.refuse(self.obs(self.submitted(), 'rerouted', reroute=event), 'context-mismatch')
        # Caller buffers a bounded early notification; it can be applied after a
        # correlated terminal establishes the worker, before qualification closes.
        terminal = self.terminal(self.submitted())
        result = self.obs(terminal, 'rerouted', reroute=event)
        self.assertFalse(result['execution_matches_request'])

    def test_malformed_data_fails_closed_without_echo(self):
        marker = 'PRIVATE-CREDENTIAL-MARKER'
        self.req[marker] = marker
        result = self.plan()
        self.refuse(result)
        self.assertNotIn(marker, json.dumps(result))
        self.req.pop(marker)
        self.req['require_different_provider'] = []
        self.refuse(self.plan())
        self.req['require_different_provider'] = False
        self.req['author_provider'] = {}
        self.refuse(self.plan())

    def test_relabelled_started_prior_cannot_reopen_retry_after_cleanup(self):
        for prior in [self.started(), self.terminal(), self.terminal(kind='failed')]:
            prior.update(status='rejected', reason='prelaunch-rejection')
            result = self.obs(prior, 'cleanup-confirmed')
            self.refuse(result)
            self.assertIsNone(result['continuation'])

    def test_prior_identity_claim_must_follow_actual_acknowledgement(self):
        running = self.started()
        running['execution_matches_request'] = True
        self.refuse(self.terminal(running), 'invalid-provenance')
        running = self.started()
        running['limitations'].remove('execution-identity-unverified')
        self.refuse(self.terminal(running), 'invalid-provenance')
        running = self.started()
        running['acknowledged'] = self.native_ack(running)
        self.refuse(self.terminal(running), 'invalid-provenance')

    def test_prior_reroute_bound_and_duplicates_validated(self):
        running = self.started()
        event = dict(worker=self.worker, from_model='opaque-17', to_model='opaque-low', reason_class='unknown', reason_code=None)
        prior = self.obs(running, 'rerouted', reroute=event)
        prior['reroutes'] *= 2
        self.refuse(self.terminal(prior))
        prior['reroutes'] = [dict(event, to_model='model-' + str(i)) for i in range(65)]
        self.refuse(self.terminal(prior))

    def test_rejected_cleanup_and_retry_records_must_be_coherent(self):
        rejected = self.obs(self.plan(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        for field, value in [('used', 0), ('limit', 2), ('source_sha256', 'd' * 64), ('next_slot', 0)]:
            prior = copy.deepcopy(rejected); prior['continuation'][field] = value
            with self.assertRaises(c.Refusal):
                a.validate_result(prior, self.policy, self.bindings, self.profiles)
        prior = self.obs(self.submitted(), 'prelaunch-rejected', signal_code='fixture-proven-no-start')
        prior['continuation'] = rejected['continuation']
        self.refuse(self.obs(prior, 'cleanup-confirmed'))

    def test_strict_json_and_size_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for data in [b'{"a":1,"a":2}', b'{"a":1.2}', b'{"a":NaN}', b'\xff', b' ' * (c.MAX_BYTES + 1)]:
                path.write_bytes(data)
                with self.assertRaises(c.Refusal): c.load(path)

    def test_projected_native_pages_complete_chain_and_exact_identifiers(self):
        first = dict(context=c.stable_context(self.ctx), cursor=None, includeHidden=False,
                     data=[dict(model='native-opaque', hidden=False,
                                supportedReasoningEfforts=[{'reasoningEffort': 'max'}])], nextCursor='page-2')
        second = dict(context=c.stable_context(self.ctx), cursor='page-2', includeHidden=False,
                      data=[dict(model='another-token', hidden=False,
                                 supportedReasoningEfforts=[{'reasoningEffort': 'high'}])], nextCursor=None)
        pages = [first, second]
        result = c.normalize_pages(pages, self.ctx)
        self.assertEqual([r['model'] for r in result], ['another-token', 'native-opaque'])
        for bad in [[first], [second, first], [first, first], [second], [first, second, second]]:
            with self.assertRaises(c.Refusal): c.normalize_pages(bad, self.ctx)
        for field, value in [('hidden', True), ('supportedReasoningEfforts', [])]:
            old = first['data'][0][field]; first['data'][0][field] = value
            with self.assertRaises(c.Refusal): c.normalize_pages(pages, self.ctx)
            first['data'][0][field] = old
        first['data'][0]['id'] = first['data'][0].pop('model')
        with self.assertRaises(c.Refusal): c.normalize_pages(pages, self.ctx)
        first['data'][0]['model'] = first['data'][0].pop('id')
        second['context']['server_instance_ref'] = 'different-instance'
        with self.assertRaises(c.Refusal): c.normalize_pages(pages, self.ctx)

    def test_v1_digest_unchanged_by_v2_namespace(self):
        before = a.v1.source_digest(self.policy, self.bindings)
        old = a.source_digest(self.policy, self.bindings, self.profiles)
        self.profile['prelaunch_codes'].append('fixture-another-signal')
        self.assertNotEqual(old, a.source_digest(self.policy, self.bindings, self.profiles))
        self.assertEqual(before, a.v1.source_digest(self.policy, self.bindings))

    def test_production_registry_explicitly_unqualified(self):
        policy, bindings, profiles = a.sources()
        self.assertEqual(profiles['profiles'], [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            path.write_text(json.dumps(dict(schema='native-dispatch-input/v2', request=self.req, evidence=self.ev, continuation=None)))
            result = subprocess.run([sys.executable, str(ROOT / 'app_server_dispatch.py'), 'plan', '--input', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.refuse(json.loads(result.stdout), 'profile-mismatch')


if __name__ == '__main__':
    unittest.main()
