// The Workers Free profile uses one Worker, one database and a Workers-first
// asset binding. This renderer is pure and never grants deployment authority.
import {profile} from './contract.mjs';

const WORKER_NAME = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const ACCOUNT_ID = /^[0-9a-f]{32}$/;
const DATABASE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
// Match the Machine Monitor reference and the supported Wrangler 4.158.0 runtime.
const COMPATIBILITY_DATE = '2026-11-07';

export function workersFreeConfig({configuration, accountId, accountSubdomain, workerName, databaseName, databaseId}) {
  const product = profile(configuration);
  if (!ACCOUNT_ID.test(accountId ?? '') || !WORKER_NAME.test(accountSubdomain ?? '') ||
      !WORKER_NAME.test(workerName ?? '') || !WORKER_NAME.test(databaseName ?? '') ||
      !DATABASE_ID.test(databaseId ?? '') || (accountId === '0'.repeat(32)) ||
      databaseId === '00000000-0000-0000-0000-000000000000') {
    throw new Error('Invalid Workers Free resource identity');
  }
  if (product.origin !== `https://${workerName}.${accountSubdomain}.workers.dev`) {
    throw new Error('Workers Free origin differs from the assigned Worker');
  }
  return {
    name: workerName,
    account_id: accountId,
    main: './delivery/worker.mjs',
    compatibility_date: COMPATIBILITY_DATE,
    workers_dev: true,
    preview_urls: false,
    vars: {RELEASE_PROFILE: JSON.stringify(product)},
    assets: {
      directory: './private-assets',
      binding: 'ASSETS',
      run_worker_first: true,
      html_handling: 'none',
      not_found_handling: 'none',
    },
    d1_databases: [{binding: 'DB', database_name: databaseName, database_id: databaseId}],
  };
}
