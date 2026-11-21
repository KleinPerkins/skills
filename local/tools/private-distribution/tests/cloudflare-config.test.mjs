import assert from 'node:assert/strict';
import {test} from 'node:test';
import {workersFreeConfig} from '../delivery/cloudflare-config.mjs';

const inputs = {
  accountId: 'a'.repeat(32), accountSubdomain: 'fictional-account',
  workerName: 'fixture-a', databaseName: 'fixture-a-state',
  databaseId: '1a1a1a1a-2b2b-4c4c-8d8d-5e5e5e5e5e5e',
  configuration: {
    app_id: 'io.example.fixture', bundle_id: 'io.example.fixture', team_id: 'EXAMPLE001',
    architecture: 'universal', minimum_macos: '15.0', data_schema_version: 1,
    origin: 'https://fixture-a.fictional-account.workers.dev',
  },
};

test('renders one exact named origin with unconditional Worker-first assets and explicit preview denial', () => {
  const configuration = workersFreeConfig(inputs);
  assert.equal(configuration.name, inputs.workerName);
  assert.equal(configuration.account_id, inputs.accountId);
  assert.equal(configuration.compatibility_date, '2026-11-07');
  assert.equal(configuration.preview_urls, false);
  assert.equal(configuration.workers_dev, true);
  assert.deepEqual(configuration.assets, {directory: './private-assets', binding: 'ASSETS',
    run_worker_first: true, html_handling: 'none', not_found_handling: 'none'});
  assert.deepEqual(configuration.d1_databases, [{binding: 'DB', database_name: inputs.databaseName,
    database_id: inputs.databaseId}]);
  assert.deepEqual(JSON.parse(configuration.vars.RELEASE_PROFILE), inputs.configuration);
});

test('rejects mismatched and alternate product origins, account and database placeholders', () => {
  assert.throws(() => workersFreeConfig({...inputs, workerName: 'fixture-b'}), /origin differs/);
  assert.throws(() => workersFreeConfig({...inputs, accountSubdomain: 'different-account'}), /origin differs/);
  for (const origin of ['https://example.invalid', 'https://fixture-a.fictional-account.workers.dev:1443']) {
    assert.throws(() => workersFreeConfig({...inputs, configuration: {...inputs.configuration, origin}}), /origin differs/);
  }
  assert.throws(() => workersFreeConfig({...inputs, accountId: '0'.repeat(32)}), /resource identity/);
  assert.throws(() => workersFreeConfig({...inputs, databaseId: '00000000-0000-0000-0000-000000000000'}), /resource identity/);
});
