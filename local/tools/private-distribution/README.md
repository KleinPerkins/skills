# Private distribution adapter

A local Skills capability for authenticated delivery of signed macOS archives.
Dev owns the repository and channel binding. Each consumer owns its product
identity, signing keys, access grants and release approval.

The Worker serves manifests, part descriptors and 256 KiB pieces behind a fresh
D1 primary authorization check. The client reads the configured origin,
verifies ordered parts, and verifies the complete SHA-256 and Ed25519 signature
before returning bytes. It accepts an explicit product, channel, artifact role,
public key and archive ceiling. The caller owns platform code-signing and
installation checks.

The publisher fixture exercises archive staging, immutable version and build
registration, exact-byte readback, qualification and stable compare-and-set,
recipient grant replacement and revocation, and recovery by pausing stable.
It runs against SQLite through explicit artifact ports. Before adopting a D1
publisher, verify atomic provider transactions and scoped roles with a
disposable sibling. The shared profile is pending live qualification.

## Owner qualification boundary

The publisher is an administrative SQLite fixture. Its caller owns the database,
artifact ports and release decision; do not expose it to recipients or untrusted
receipt submitters. As in the pinned Machine Monitor publisher, qualification is
an owner-vetted receipt, not an independently authenticated attestation.

Before calling `promote`, the owner must verify `ci_required`, `merged_source`,
`developer_id`, `notarization`, `stapled_ticket`, `gatekeeper`, `archive_signature`,
`recovery_packaged` and an actual `private_upgrade` for the exact staged artifacts.
The closed `private-distribution/qualification/v1` receipt requires every check to
be boolean `true` and binds the product, release, build, source revision,
qualification ID, and both artifact hashes and sizes. `evidence_sha256` records an
owner-retained evidence reference; its format check does not authenticate evidence
or prove that a check ran. The owner must retain and inspect that evidence.

The adapter rechecks exact signed archive bytes and enforces the channel transition.
It cannot prevent a privileged owner from lying about checks or directly editing
its database. Synthetic test receipts prove validation and state transitions only;
consumer signing, live provider qualification and product release gates remain
separate.

## Verify the source

Use Node 24 with `node:sqlite` and run from the tool directory.

```sh
./install.sh --check
```

The tests exercise the Worker, publication state and an archive recipient with
synthetic assets and generated test keys. All resources live in memory or
test-owned temporary storage. To reuse the transport, import
`delivery/client.mjs` or deploy the qualified `delivery/worker.mjs` configuration
under the authorized provider plan. `delivery/schema.sql` is the shared schema
for the synthetic Worker and publisher.

`delivery/cloudflare-config.mjs` renders the approved Worker-first serving
shape for a supplied account subdomain, Worker and D1 identity. It produces
configuration for source review and later provider preflight. Verify the
actual account plan, effective roles, routing, resource isolation and
atomic publication before enabling a real consumer.

## Source provenance

KleinPerkins approved adapting its pinned Machine Monitor delivery source for
this capability. The Worker, wire validators, SQL, archive client, and publisher
derive from `delivery/` and `scripts/delivery.py` at revision
[`4f26c15527ef6912434e3953de6169aed8244e28`](https://github.com/KleinPerkins/machine-monitor/tree/4f26c15527ef6912434e3953de6169aed8244e28).
The generic protocol uses the `private-distribution/` schema namespace. The
existing Machine Monitor protocol and its releases keep their original scope.
The [source license](MACHINE-MONITOR-LICENSE.txt) and
[upstream notices](MACHINE-MONITOR-THIRD-PARTY-NOTICES.md) accompany the adaptation.
