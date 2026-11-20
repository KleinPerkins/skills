"""Closed group and exact-run receipt regressions; fixture-only, no CI/API writes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('skills_ci',ROOT/'scripts/verify.py')
ci=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(ci)

class DeliveryTests(unittest.TestCase):
    def fixture(self):
        c,m,h=ci.policy();identity={'fixture':'exact-run'};needs={}
        for s in ci.SHARDS:
            row=next(x for x in m['shards'] if x['id']==s)
            measurement={'commands':[x['id'] for x in c['commands'][s]],'coverage':row['coverage'],'logs_sha256':'a'*64,'contract_sha256':h}
            receipt={'schema':'skills-ci-shard/v1','shard':s,'identity':identity,'result':'success','measurement':measurement}
            needs[s]={'result':'success','outputs':{'receipt':json.dumps(receipt)}}
        return needs,identity,h
    def test_complete_current_run(self):
        needs,identity,h=self.fixture();self.assertEqual(ci.validate_aggregate(needs,identity),h)
    def test_missing_extra_failed_cancelled_skipped_or_empty_shard_refuses(self):
        needs,identity,_=self.fixture()
        for status in ('failure','cancelled','skipped',''):
            bad=copy.deepcopy(needs);bad['baseline']['result']=status
            with self.subTest(status=status),self.assertRaises(ci.ContractError):ci.validate_aggregate(bad,identity)
        for bad in ({},dict(needs,extra=needs['baseline']),{k:v for k,v in needs.items() if k!='save-game'}):
            with self.assertRaises(ci.ContractError):ci.validate_aggregate(bad,identity)
    def test_stale_identity_measurement_or_contract_refuses(self):
        needs,identity,_=self.fixture()
        for key in ('identity','shard','result','schema'):
            bad=copy.deepcopy(needs);r=json.loads(bad['baseline']['outputs']['receipt']);r[key]='stale';bad['baseline']['outputs']['receipt']=json.dumps(r)
            with self.subTest(key=key),self.assertRaises(ci.ContractError):ci.validate_aggregate(bad,identity)
        for key in ('commands','coverage','logs_sha256','contract_sha256'):
            bad=copy.deepcopy(needs);r=json.loads(bad['baseline']['outputs']['receipt']);r['measurement'][key]=[] if key in ('commands','coverage') else 'bad';bad['baseline']['outputs']['receipt']=json.dumps(r)
            with self.subTest(key=key),self.assertRaises(ci.ContractError):ci.validate_aggregate(bad,identity)
    def test_real_repo_identity_and_merge_ref_required(self):
        env=dict(GITHUB_REPOSITORY='KleinPerkins/skills',GITHUB_REPOSITORY_ID='1461925043',GITHUB_EVENT_NAME='pull_request',GITHUB_SHA='c'*40,GITHUB_WORKFLOW_SHA='c'*40,GITHUB_RUN_ID='1',GITHUB_RUN_ATTEMPT='1',GITHUB_REF='refs/pull/1/merge',CI_HEAD_SHA='a'*40,CI_BASE_SHA='b'*40,GITHUB_WORKFLOW_REF='KleinPerkins/skills/.github/workflows/ci.yml@refs/pull/1/merge',GITHUB_WORKFLOW='CI')
        self.assertEqual(ci.identity(env)['revision'],'c'*40)
        for k,v in [('GITHUB_REPOSITORY_ID','1459458379'),('GITHUB_REPOSITORY','KleinPerkins/dev'),('GITHUB_SHA','a'*40),('GITHUB_REF','refs/heads/main'),('CI_BASE_SHA',''),('GITHUB_RUN_ATTEMPT','0')]:
            with self.subTest(key=k),self.assertRaises(ci.ContractError):ci.identity(dict(env,**{k:v}))
    def test_every_meaningful_entrypoint_has_one_owner(self):
        c,_,_=ci.policy()
        self.assertEqual([x['argv'] for x in c['commands']['baseline']],[['bash','.github/scripts/verify-skills.sh']])
        self.assertEqual([x['argv'] for x in c['commands']['save-game']],[['make','-C','global/skills/save-game','test']])
        self.assertEqual([x['id'] for x in c['commands']['capability-tests']],['swarm-full','keep-awake','consolidator','delivery-admission'])
        self.assertEqual(c['commands']['capability-tests'][0]['argv'],['bash','global/skills/swarm/tests/run_tests.sh'])
        baseline=(ROOT/'.github/scripts/verify-skills.sh').read_text()
        self.assertIn('--portable-source-contract',baseline)
        self.assertIn('macOS runtime',baseline)
    def test_inventory_and_baseline_drift_refuse(self):
        with tempfile.TemporaryDirectory() as raw:
            target=Path(raw)
            import shutil
            for rel in ('.github/ci-contract.json','.github/test-shards.json','.github/scripts/verify-skills.sh'):
                p=target/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/rel,p)
            (target/'.github/scripts/verify-skills.sh').write_text('exit 0\n')
            with self.assertRaises(ci.ContractError):ci.policy(target)
    def test_duplicate_json_and_work_only_review_policy(self):
        with self.assertRaises(ci.ContractError):ci.parse('{"x":1,"x":2}')
        p=json.loads((ROOT/'.github/review-enrollments.json').read_text())
        self.assertEqual(p['repository_id'],1461925043)
        self.assertEqual(p['repository_names'],['KleinPerkins/skills'])
        self.assertTrue(p['enabled'])
        self.assertEqual({x['origin_account'] for x in p['producers'] if x['enabled']},{'origin-7612de79'})
        self.assertEqual({x['credential_store'] for x in p['producers']},{'file','keyring'})
        self.assertTrue(all(x['creation_adapter_sha256']==hashlib.sha256((ROOT/'scripts/create_review_pr.py').read_bytes()).hexdigest() and x['capture_adapter_sha256']==hashlib.sha256((ROOT/'scripts/local_review.py').read_bytes()).hexdigest() for x in p['producers']))
    def test_workflow_all_groups_aggregate_and_no_privilege(self):
        workflow=json.loads((ROOT/'.github/workflows/ci.yml').read_text())
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertEqual(set(workflow['jobs']),set(ci.SHARDS)|{'ci-required'})
        self.assertEqual(workflow['jobs']['ci-required']['needs'],list(ci.SHARDS))
        for s in ci.SHARDS:
            job=workflow['jobs'][s]
            self.assertEqual(job['runs-on'],'ubuntu-24.04')
            self.assertEqual(job['steps'][-1]['run'],'python3 -I -B scripts/verify.py shard --shard '+s)
            self.assertEqual(job['outputs'],{'receipt':'${{ steps.verify.outputs.receipt }}'})
        self.assertIn('always()',workflow['jobs']['ci-required']['if'])
        self.assertNotIn('pull_request_target',workflow['on'])
        self.assertNotIn('secrets.',json.dumps(workflow))

if __name__=='__main__':unittest.main()
