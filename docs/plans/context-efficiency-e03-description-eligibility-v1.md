# Context Efficiency E-03 — strict skill-description eligibility

**Version:** v1
**Status:** ACCEPTED — 2026-08-15
**Date:** 2026-08-15
**Owning repository:** `skills` (`KleinPerkins/skills`)
**Program milestone:** E-03, “Establish strict description-inventory eligibility.”
**Review provenance:** Authored from the accepted Context Efficiency Program and ADR 0004, then grounded against clean Skills `origin/main`, every tracked Skills-owned `SKILL.md`, the current verifier, and the locked runnerless recipe. No description total was calculated from the malformed baseline, and no implementation or client install was changed while authoring this draft.

**Goal:** Make every Skills-owned skill descriptor eligible for deterministic inventory by requiring valid YAML 1.2 Core-schema frontmatter, fixing the current `update-skills` syntax defect, and implementing `skill-description-normalization/v1` as one strict, fail-closed source-evidence path.

**Architecture:** Add one repository-local, standard-library inventory program with a bounded YAML 1.2 Core profile, deterministic candidate discovery, and versioned conformance fixtures. It parses the first exact frontmatter document, normalizes only the parsed `description`, and emits a complete deterministic inventory only after every candidate succeeds. Malformed or unsupported input returns `BLOCKED_PREREQUISITE` with no partial rows or totals. The existing line-oriented shell checks may remain as non-authoritative name/path guards but can never substitute for the strict parser.

**Tech stack:** Python 3 standard library, JSON conformance fixtures, existing Bash verifier, and the current Skills bootstrap for post-merge client reconciliation.

---

## 1. Authority and exact dependency binding

This draft is bound to:

| Authority | Exact ref | Bound evidence |
|---|---|---|
| Skills live default branch | `KleinPerkins/skills` `main` at `54537b040e837a00543414e4efacd1b3f3f959b7` | Clean isolated worktree; rollback/source baseline |
| Accepted Dev program | `KleinPerkins/dev` `main` at `0818be2f3beb0bfafaa17abd6250e780f87a19a1` | `_ops/plans/context-efficiency-program-v1.md` blob `f6de269c9c2f88e78e58abd9c247405cb506a123`, raw SHA-256 `327a87b930a9d26a62388005db39c2b097660e0ebfd95aa01d80b17819c17cc4` |
| Accepted ADR 0004 | Same Dev commit | `_ops/adr/0004-optimize-context-projections-without-moving-authority.md` blob `0578f7d7b4ace6c233d5f56c9d20fc43ad979450`, raw SHA-256 `77ddcd3b5e480b77cf283afd8e5593b08022483920ff55451bf5d79fcfc51060` |

The Skills changes after the program’s prior `9fa02b9c0d34a554e32994e9258e6241fc1f3c90` audit are runnerless PR-automation proof/configuration only. The descriptor set, malformed `update-skills` frontmatter, and verifier behavior remain as assumed.

Implementation must refresh `origin/main` and re-enumerate candidates before editing. A material change to descriptor layout, parser availability assumptions, the protected recipe, or the accepted normalization contract requires re-adjudication or a successor plan; do not silently broaden the parser or add a permissive fallback.

## 2. Global constraints and protected invariants

- This DRAFT is planning-only. No parser, normalizer, fixture, descriptor, install, or client mutation is authorized until owner acceptance.
- Implement exactly one authoritative description parser/normalizer. No fallback line parser, alternate client parser, best-effort mode, or partial inventory may emit rows or totals.
- Add no registry, runtime, daemon, router, context manager, or delivery channel. The inventory is deterministic evidence and a repository verifier, not an enrollment or client-loading authority.
- Candidate discovery derives from tracked source paths; it does not become a hand-maintained list.
- Fix only the invalid `argument-hint` syntax in `local/skills/update-skills/SKILL.md`. Do not shorten or semantically rewrite its `description` in E-03.
- Do not implement the 300-character warning, 600-character failure, or 1,024-character migration ceiling here. Those optimization/budget decisions belong to later D-01/D-02 work after eligibility.
- Exact normalized duplicates are a strict eligibility failure because the accepted contract requires exact normalized-string comparison; fuzzy similarity and routing-quality judgments remain out of scope.
- Preserve every capability’s `meta.yml`, ID, kind, scope, exposure, provenance, payload, and install path.
- Preserve Save-Game, `agent-route`, ordinary-language access, and model-tier/orchestration semantics. Add no context-specific router.
- Do not inspect, print, classify, rewrite, or delete `agent-learnings.md`, generated `~/AGENTS.md`, or any private operator data.
- Do not change CPP-local descriptors or hand-vendor any payload downstream.
- Use one writer per tree, the Skills governed PR path, and the reviewer App’s merge gate. Agents must not arm auto-merge.

## 3. Verified current state and blocker

At the bound Skills ref:

- There are 29 tracked `SKILL.md` descriptors below `global/` and `local/`, including direct skills, plugin skills, and the packaged Operator Voice skill installed by its existing tool installer.
- A read-only diagnostic parse found 28 syntactically parseable descriptors and one blocker. This was syntax triage only; it was not used to calculate normalized strings, duplicate results, or totals.
- `local/skills/update-skills/SKILL.md:5` currently contains:

```yaml
argument-hint: [optional: "skills only" or "rules only"]
```

The colon inside that flow sequence makes the frontmatter invalid YAML. The intended UI hint can be preserved byte-for-byte as a string by quoting the whole value:

```yaml
argument-hint: '[optional: "skills only" or "rules only"]'
```

- `.github/scripts/verify-skills.sh:119-140` deliberately checks only delimiter structure, one `name`, one `description`, and name-to-ID equality with `awk`. It explicitly does not parse block scalars or measure descriptions, so the malformed file currently passes.
- Plugin descriptors and the packaged Operator Voice descriptor are not covered by that skill-kind shell block, even though clients can discover them.
- `.github/pr-recipe.json` runs `.github/scripts/verify-skills.sh` as the protected `repo.skills.m3-verify` job in a network-disabled, standard-library-oriented environment. E-03 must not add a network-time package install or mutate the protected recipe.

Because one candidate is malformed, the authoritative baseline state is `BLOCKED_PREREQUISITE`. No current exact description total is valid.

## 4. Strict inventory contract

### 4.1 Candidate set

`discover_candidates(repo_root)` must use Git’s tracked-file inventory and select every path matching:

```text
global/**/SKILL.md
local/**/SKILL.md
```

Order paths by raw UTF-8 path bytes (`LC_ALL=C` semantics). Do not filter by a new registry, current client exposure, or capability kind: a tracked Skills-owned descriptor that can be packaged or installed must be valid even if a later inventory classifies a client as ineligible. Conformance fixtures use `.json` payloads rather than tracked files named `SKILL.md`, so they never enter the repository candidate set.

Compare that tracked set with the physical `global/**/SKILL.md` and `local/**/SKILL.md` set. An empty candidate set, an untracked descriptor in an otherwise clean release candidate, a tracked-but-missing descriptor, or inability to read the Git inventory is `BLOCKED_PREREQUISITE`.

### 4.2 Authoritative parser profile

Implement one repository-local parser in `scripts/skill-description-inventory.py`. It must use only the Python standard library available to the locked verifier and accept a deliberately bounded subset of YAML 1.2 Core sufficient for every tracked descriptor shape:

- a top-level block mapping with unique string keys;
- nested block mappings;
- Core-schema plain, single-quoted, and double-quoted scalars;
- flow sequences with correctly quoted or valid Core scalar members;
- literal and folded block scalars with indentation and `strip`/`clip`/`keep` chomping;
- comments and blank lines where YAML 1.2 permits them.

Any construct outside the bounded profile—including otherwise valid YAML—is fail-closed `BLOCKED_PREREQUISITE` until the owner explicitly extends the parser and its conformance fixtures. Anchors, aliases, explicit tags, merge keys, directives, duplicate keys, tab indentation, malformed escapes/flows, and additional YAML documents are not needed by the current source and must be rejected rather than guessed.

This profile is a strict subset of YAML 1.2 Core: every accepted document is valid YAML 1.2 Core, but the parser need not accept every legal YAML feature. It is the sole parser, not a fallback. Do not condition behavior on whether PyYAML, Ruby, Node, or another ambient package happens to be installed.

The input contract is:

1. Read raw bytes and record SHA-256.
2. Decode strict UTF-8; invalid bytes block.
3. Require `---` as the exact first line and the first later exact `---` line as the closing frontmatter delimiter.
4. Parse the complete enclosed document as one top-level mapping under the bounded YAML 1.2 Core profile.
5. Require exactly one `description` whose native parsed value is a string. Missing, duplicate, null, boolean, numeric, sequence, or mapping descriptions block.

### 4.3 `skill-description-normalization/v1`

For each parsed description:

1. Use the YAML string after native quote handling and block-scalar folding/chomping.
2. Preserve every Unicode scalar value exactly; perform no NFC/NFKC or other Unicode normalization.
3. Replace each maximal run of this pinned Unicode 15.0 `White_Space` set with one U+0020:
   - U+0009–U+000D
   - U+0020
   - U+0085
   - U+00A0
   - U+1680
   - U+2000–U+200A
   - U+2028, U+2029, U+202F
   - U+205F
   - U+3000
4. Trim leading/trailing U+0020.
5. Count Unicode scalar values in the normalized result.
6. Compare exact normalized strings across candidates; any duplicate group blocks the inventory.

Zero-width or non-listed code points remain untouched. Strict UTF-8 prevents surrogate code points, so Python code-point length is the required Unicode-scalar count.

### 4.4 Program and CLI interfaces

Create these importable interfaces in `scripts/skill-description-inventory.py`:

```text
discover_candidates(repo_root: Path) -> list[Path]
parse_frontmatter(raw: bytes, source_path: str) -> dict[str, object]
normalize_description(value: str) -> str
build_inventory(repo_root: Path) -> dict[str, object]
main(argv: list[str] | None = None) -> int
```

CLI:

```bash
python3 scripts/skill-description-inventory.py --repo .
```

Exit/output contract:

- `0`: write one deterministic UTF-8 JSON document plus final newline to stdout.
- `2`: invalid CLI invocation; normal argparse diagnostic.
- `3`: write one or more `BLOCKED_PREREQUISITE <path>: <plain reason>` lines to stderr and write **zero bytes** to stdout.

The success JSON is `skill-description-inventory/v1` and contains:

- `normalization_contract: skill-description-normalization/v1`;
- `parser_profile: skills-yaml12-core-profile/v1`;
- `whitespace_set: unicode-15.0-white-space`;
- conformance-fixture version and SHA-256;
- ordered candidate rows with source path, raw source SHA-256, frontmatter name, normalized description, normalized SHA-256, and Unicode-scalar character count;
- candidate count, exact normalized duplicate result, and total normalized characters.

It contains no timestamp or absolute checkout path, so unchanged source and fixtures produce byte-identical output. Build the complete object in memory and write stdout only after all candidates and duplicate checks pass. Diagnostics may identify paths and failure classes but must never print a partial normalized inventory or total.

## 5. Exact file map and rollback boundary

Implementation is limited to:

- Modify `local/skills/update-skills/SKILL.md:5` — quote the existing `argument-hint` as one YAML string; no description/body change.
- Create `scripts/skill-description-inventory.py` — sole strict parser, normalizer, deterministic inventory CLI.
- Create `scripts/tests/test_skill_description_inventory.py` — parser, normalizer, discovery, duplicate, failure, and repository integration tests.
- Create `scripts/tests/fixtures/skill-description-normalization-v1/cases.json` — versioned raw-byte/expected-result conformance cases.
- Modify `.github/scripts/verify-skills.sh:119-140,260-291` — retain the narrow name/path guard, add the strict conformance suite and repository inventory gate, and ensure strict failure controls the verifier exit.

Do not modify `.github/pr-recipe.json`, `.github/pr-automation*.json`, any `meta.yml`, `.eco-registry.lock`, bootstrap logic, installed symlink, generated catalog, or downstream copy.

E-01 is a separate implementation/rollback boundary. Both plans add independent stanzas to `.github/scripts/verify-skills.sh`; whichever implementation lands second must rebase and preserve the first.

## 6. Work items

### Task 1: Pin the parser and normalization contract with red fixtures

**Files:**

- Create `scripts/tests/fixtures/skill-description-normalization-v1/cases.json`
- Create `scripts/tests/test_skill_description_inventory.py`
- Create `scripts/skill-description-inventory.py` with signatures/constants only as needed for the tests to import

**Interfaces:**

- Consumes: §4’s exact parser/normalization contract and raw fixture bytes.
- Produces: versioned, deterministic conformance tests that distinguish parsed YAML value, normalized value, scalar count, duplicate identity, and blocked input.

- [ ] Give `cases.json` its own `skill-description-normalization-fixtures/v1` schema and store raw input as base64 so CRLF, bare CR, invalid UTF-8, tabs, and trailing newlines survive Git unchanged.
- [ ] Include valid plain, single-quoted, double-quoted, nested-mapping, and flow-sequence documents.
- [ ] Include folded/literal block scalars for `strip`, `clip`, and `keep`, asserting the native parsed string before normalization as well as the final normalized string.
- [ ] Include every pinned Unicode whitespace scalar in one case, U+200B as a preserved non-whitespace control, composed/decomposed Unicode as non-normalized controls, and an astral scalar proving one-character counting.
- [ ] Include YAML 1.2 Core typing controls: `yes`/`no`/`on`/`off` remain strings, while `true`, `false`, `null`, and numeric `description` values block as non-string.
- [ ] Include missing/open/extra document delimiters, missing/duplicate description, duplicate mapping keys, invalid flow syntax matching the current `argument-hint`, bad indentation/escapes, aliases/anchors/tags/directives, and invalid UTF-8.
- [ ] Include two distinct source documents whose descriptions normalize identically and require duplicate blocking.
- [ ] Assert every blocked case exits/raises the same `BLOCKED_PREREQUISITE` class and cannot produce inventory stdout/totals.

Focused red command:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_skill_description_inventory.py' -v
```

Expected before implementation: parser/normalizer contract tests fail because the new interfaces do not yet exist or are stubs.

### Task 2: Implement the single strict path and prove malformed input cannot emit totals

**Files:**

- Complete `scripts/skill-description-inventory.py`
- Extend `scripts/tests/test_skill_description_inventory.py`

**Interfaces:**

- Consumes: Task 1 fixtures and tracked Git candidate paths.
- Produces: deterministic `skill-description-inventory/v1` JSON only when every candidate is eligible.

- [ ] Implement the bounded YAML 1.2 Core profile without ambient/external packages.
- [ ] Implement the exact Unicode whitespace set and maximal-run replacement without Unicode normalization.
- [ ] Discover all tracked `global/**/SKILL.md` and `local/**/SKILL.md` paths in deterministic order.
- [ ] Accumulate failures and withhold stdout until the complete candidate set and duplicate check are green.
- [ ] Add a subprocess test that captures stdout/stderr/exit status for malformed input and requires exit `3`, empty stdout, and a plain `BLOCKED_PREREQUISITE` diagnostic.
- [ ] Add a deterministic-output test that runs the same valid fixture inventory twice and compares bytes.
- [ ] Add a source-digest mutation test proving any changed candidate changes only its bound row and aggregate bytes.

Repository red command before fixing `update-skills`:

```bash
out="$(mktemp)"
err="$(mktemp)"
if python3 scripts/skill-description-inventory.py --repo . >"$out" 2>"$err"; then
  rc=0
else
  rc=$?
fi
test "$rc" -eq 3
test ! -s "$out"
grep -F 'BLOCKED_PREREQUISITE local/skills/update-skills/SKILL.md:' "$err"
rm -f "$out" "$err"
```

Expected: exit `3`, zero stdout bytes, and the invalid-flow diagnostic. No normalized character total is available.

### Task 3: Fix the one source defect and wire the owner verifier

**Files:**

- Modify `local/skills/update-skills/SKILL.md`
- Modify `.github/scripts/verify-skills.sh`

**Interfaces:**

- Consumes: the strict CLI and existing protected verifier.
- Produces: one green repository eligibility gate; no new delivery or client-loading behavior.

- [ ] Replace only line 5 with:

```yaml
argument-hint: '[optional: "skills only" or "rules only"]'
```

- [ ] Add the focused Python suite to `.github/scripts/verify-skills.sh`.
- [ ] Run the strict repository inventory after the suite. Redirect success JSON to a temporary file or `/dev/null`; never parse a failure with `awk` to recover partial totals.
- [ ] Update the existing shell comment to state that its name/path checks are supplementary and non-authoritative. It must not claim YAML validity or description measurement.
- [ ] Require either strict-test or inventory failure to set the repository verifier’s existing `fail=1`.

Focused green commands:

```bash
python3 -m unittest discover -s scripts/tests -p 'test_skill_description_inventory.py' -v
python3 scripts/skill-description-inventory.py --repo . > /tmp/skill-description-inventory.json
cmp /tmp/skill-description-inventory.json <(python3 scripts/skill-description-inventory.py --repo .)
rm -f /tmp/skill-description-inventory.json
```

Expected: all conformance tests pass; both successful inventory byte streams match; the success document binds all 29 current candidates and the fixture/source digests. Exact normalized totals may be recorded only at this green point.

Required full command:

```bash
bash .github/scripts/verify-skills.sh
```

Expected: explicit `PASS` lines for strict description conformance and repository inventory, followed by `verify-skills: OK (global + local + lock + capability-local)`.

The red fixtures, strict implementation, source syntax fix, and verifier wiring land in one implementation PR; do not commit a failing intermediate repository state.

### Task 4: Prove install, upgrade, repair, idempotence, and failure paths

**Files:**

- No files beyond §5.

**Interfaces:**

- Consumes: merged-candidate source, standard bootstrap, isolated HOME, and the locked runnerless recipe.
- Produces: owner verification evidence and a release candidate bound to exact bytes.

- [ ] **Clean source/install:** in a fresh clone and isolated HOME, run the inventory, `bootstrap.sh --reconcile`, focused tests, and full verifier. Require only valid, durable client descriptors.
- [ ] **In-place upgrade:** start from the bound pre-fix checkout with Cursor/Claude `update-skills` links, advance to the candidate source, run the standard reconcile, and prove the links now expose the corrected exact bytes without changing description semantics.
- [ ] **Repair:** delete or stale the isolated Cursor/Claude `update-skills` links, run `bootstrap.sh --repair`, and require links to the candidate source; do not hand-copy the descriptor.
- [ ] **Idempotence:** run inventory twice for byte equality and run reconcile/repair twice with no second-order source or link changes.
- [ ] **Failure:** replace one candidate in a disposable checkout with each malformed/non-string/duplicate fixture class; require full verifier failure, exit `3` from the inventory, and zero inventory stdout/totals.
- [ ] **No-fallback proof:** include a malformed document that satisfies the existing delimiter/key-count `awk` guard; the strict gate must still fail the full verifier.
- [ ] Run shell/Python syntax checks and full verification:

```bash
python3 -m py_compile scripts/skill-description-inventory.py scripts/tests/test_skill_description_inventory.py
bash -n .github/scripts/verify-skills.sh
python3 -m unittest discover -s scripts/tests -p 'test_skill_description_inventory.py' -v
bash .github/scripts/verify-skills.sh
```

- [ ] Run documentation governance read-only and record unrelated baseline drift separately:

```bash
/Users/laurence.duggan/dev/_ops/bin/doc-warden.sh check "$(git rev-parse --show-toplevel)"
```

- [ ] Record the implementation commit, parser file SHA-256, fixture SHA-256, corrected descriptor SHA-256, and successful inventory SHA-256. Any changed parser/fixture/descriptor byte invalidates exact-candidate approval.
- [ ] Open the implementation PR through Skills’ ordinary governed path. Require the exact-head `pr-automation / verify`; do not arm auto-merge.

### Task 5: Reconcile affected clients only after operator GO

**Files:**

- No repository edits; machine-local client links are reconciled through the existing bootstrap only.

**Interfaces:**

- Consumes: exact merged Skills commit, successful strict inventory, standard bootstrap dry-run, and explicit operator GO.
- Produces: fresh Cursor/Claude discovery evidence plus content-safe program evidence.

- [ ] Verify the established Skills primary is at the approved merged commit and re-run strict inventory/full verification.
- [ ] Preview the standard reconciliation in the operator HOME:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile --dry-run
```

- [ ] Present the merged commit, parser/fixture/inventory digests, and preview. Apply only after explicit machine-local release GO:

```bash
bash "${HOME}/dev/capabilities/skills/bootstrap.sh" --reconcile
```

- [ ] Confirm `~/.cursor/skills/update-skills` and `~/.claude/skills/update-skills` resolve to the approved source and exact corrected descriptor bytes.
- [ ] Run only the affected fresh-client rows in §8.
- [ ] Record refs, digests, candidate count, normalized total, duplicate result, and client evidence in the Dev evidence ledger. Do not record private memory or make the ledger an enrollment authority.

## 7. Approval, owner, exact-digest, release, and machine-local gates

| Gate | Required evidence and authority | Failure behavior |
|---|---|---|
| Dependency/ref gate | Skills owner ref and accepted Dev commit/blobs/digests remain valid | Stop; revise/supersede |
| Owner-plan gate | Operator accepts this DRAFT under Skills’ plan lifecycle; accepted bytes freeze | No implementation while DRAFT |
| Parser/fixture exact-digest gate | Operator reviews the exact parser profile, parser SHA-256, fixture SHA-256, corrected descriptor SHA-256, and candidate-set rule | Any byte/semantic change revokes GO |
| Owner PR gate | Skills exact-head required check passes and reviewer App governs merge | No merge or downstream use |
| Release-GO gate | Skills has no separate semver release for this verifier. Release GO is explicit operator approval to treat the exact merged commit/inventory contract as E-03 evidence | E-03 remains blocked |
| Machine-local gate | Operator approves the bootstrap dry-run before Cursor/Claude links are reconciled | No HOME mutation |
| Live-client gate | Fresh Cursor and Claude discovery/load evidence passes for the corrected descriptor | Stop rollout; restore approved source/link and keep baseline blocked |
| Program evidence gate | Dev ledger records exact owner/parser/fixture/source/inventory refs and client eligibility without becoming executable | E-03/E-09 remain incomplete |

Acceptance of this plan satisfies only the owner-plan gate.

## 8. Fresh-client evidence rows

Only the changed descriptor’s exposed clients are affected. `local/skills/update-skills/meta.yml` exposes Cursor and Claude, not Codex; therefore no Codex canary or false Codex-support claim belongs in E-03.

| Affected cohort | Required evidence |
|---|---|
| Cursor Desktop, fresh Dev root | Skills category/autocomplete discovers `update-skills`; loading it with an explicit no-action/help prompt succeeds; an ordinary-language “which skill handles updating my installed skills—do not run it” routes to `update-skills`; displayed argument hint preserves `[optional: "skills only" or "rules only"]` |
| Claude, fresh process | `update-skills` is discovered from the approved Skills source; explicit no-action/help load and the same ordinary-language identification succeed; no install/update action is executed during the canary |

Cursor Cloud is ineligible because this is a user-home local skill. Background/multi-root context-size claims are not part of E-03.

## 9. Acceptance criteria and E-03 definition-of-done map

- Every tracked `global/**/SKILL.md` and `local/**/SKILL.md` candidate passes the bounded YAML 1.2 Core profile.
- The current `update-skills` invalid flow syntax is corrected by quoting only `argument-hint`; its description and body are unchanged.
- `skill-description-normalization/v1` exactly implements native YAML string extraction, the pinned whitespace set, no Unicode normalization, scalar counting, and exact duplicate comparison.
- Conformance fixtures cover current source shapes, Core typing, every whitespace scalar, block folding/chomping, Unicode controls, invalid UTF-8/YAML, non-string descriptions, and duplicate normalization.
- Any malformed, unsupported, missing, non-string, or duplicate input returns exit `3`, prints `BLOCKED_PREREQUISITE`, and emits zero inventory stdout/rows/totals.
- Successful inventory records parser/fixture version and digest plus every source digest in deterministic order.
- No description budget, shortening, scoping, registry, router, runtime, or alternate delivery path is added.
- Focused tests and full `.github/scripts/verify-skills.sh` pass at the exact implementation commit.
- Clean install, in-place upgrade, repair, idempotence, and fail-closed cases pass.
- Fresh Cursor and Claude evidence passes; Codex is correctly omitted because the changed skill is not exposed there.
- Save-Game, `agent-route`, model-tier/orchestration semantics, exposures, learned-data boundaries, and downstream authority remain unchanged.
- Dev receives content-safe evidence and may mark E-03 green. E-09 remains blocked until every other Release 0 prerequisite is independently green.

## 10. Clean-state receipts

Before implementation edits:

```bash
git fetch origin --prune
git status --short
git rev-parse origin/main
git diff --check
```

Expected: empty status, refreshed owner baseline, no diff errors.

Before implementation PR:

```bash
git status --short
git diff --check
git diff --name-only origin/main...HEAD
git rev-parse HEAD
```

Expected changed-file set:

```text
.github/scripts/verify-skills.sh
local/skills/update-skills/SKILL.md
scripts/skill-description-inventory.py
scripts/tests/fixtures/skill-description-normalization-v1/cases.json
scripts/tests/test_skill_description_inventory.py
```

The release receipt records the merged Skills commit; parser, fixture, descriptor, and successful inventory SHA-256 values; deterministic test/verifier results; machine reconciliation result; affected client/root classes; and rollback ref. It contains no private memory, credentials, raw client context, or learned content.

## 11. Rollout and rollback

Roll out in this order: accepted owner plan → exact parser/fixture/source candidate review → governed Skills PR/check/merge → successful strict inventory → operator-approved machine dry-run/reconcile → fresh Cursor canary → fresh Claude canary → Dev evidence.

If the parser or client canary is wrong:

1. Stop using the inventory for program totals; report `BLOCKED_PREREQUISITE`.
2. Revert the implementation commit through the Skills governed PR path or advance to a separately approved corrective commit.
3. Reconcile client links from the last approved durable Skills source and restart affected clients.
4. Never restore a permissive/fallback parser or publish partial totals. A rollback to the pre-fix ref intentionally re-blocks E-03/E-09 until a corrected strict implementation lands.

No rollback action edits learned data, generated memory, AWA, Save-Game state, client plugin caches, or downstream payloads. Closing or reverting this DRAFT planning PR changes no runtime state. Once accepted, v1 is byte-immutable; a material revision requires `context-efficiency-e03-description-eligibility-v2.md` with `Supersedes:`.
