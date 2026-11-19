# ShadowSync

ShadowSync is a source-built native macOS status utility for safely Fast-forwarding the actual
remote default branch in an explicitly authorized local clone.

This directory is the canonical Flavor-1 source. It uses Swift, AppKit, Carbon, Darwin/POSIX APIs,
and `/usr/bin/git`; it has no package dependencies, updater, scheduler, telemetry, or payload
directory.

The application icon uses the operator-selected Phase Tiles composition: an unchanged midnight
macOS squircle, rear violet tile, and front cyan tile with one centered pale-cyan Lucide
`git-pull-request-draft` glyph at 47.0% of the front tile's width. Its exact round-stroke geometry
is pinned to Lucide 1.47.0 under the ISC license in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The committed 1024px master is packaged
deterministically into `ShadowSync.icns`; production builds copy the verified committed bytes
before signing.

## ShadowSync v3 — selection first

Opening ShadowSync now shows a bounded repository chooser immediately. This first screen reads
only the governed repository catalog and saved selection intent: it starts no Git, `gh`, helper,
network, repository-inspection, or run-authority work. Eligible saved defaults are editable in the
same chooser. **Save as defaults** uses identity-and-revision conflict detection and atomic private
state; malformed preferences require a separate **Recover defaults** confirmation and the original
bytes are retained in a recovery slot. Unsupported or unsafe preference state remains read-only and
is never silently reset.

**Continue** closes chooser admission, rereads the current policy and catalog, and binds each
logical selection through no-follow governed-root descriptors. Only those repositories are then
hydrated. A first selected pass may propose canonical authority but cannot create cards or
operations; after any explicit authority confirmation, a fresh selected-only pass must establish
the verified capability used by cards, review, workers, removals, and per-node Body 3 refresh.
Foreign or unselected results are refused before state or child admission. Disabled chooser/card
rows never enter confirmations or worker payloads.

During selected hydration the chooser reports progress. **Cancel** acknowledges immediately,
closes future child admission, and stays in a cancelling state until owned work and authority have
settled. **Quit** uses the same lifecycle drain: task settlement, every child reap, worker
post-reap, Body 3 and confirmation settlement, preference outcome, and authority release are all
required before termination. From cards or reports, **Change/Manage saved selection** returns to the
process-free chooser.

## ShadowSync v2 — Body 2

Repository cards now inventory every local branch, detached worktree, physical path, claim,
upstream, exact default-branch relation, tip date, pull-request association, purpose, and
centralized activity band without checking anything out. The optional GitHub context comes only
from one identity-verified Homebrew `gh pr list` child using a closed read-only argument and
environment contract. Missing, changed, unauthenticated, offline, rate-limited, timed-out,
truncated, or malformed GitHub context is shown as unavailable and never blocks a Git operation.

The only metadata controls are explicit, operator-selected operations for the three approved
states:

- **Repair stale registration** prunes the exact final selected set of absent, inactive,
  non-default registrations under the shared common-directory lock while preserving every ref.
- **Repair moved worktree** reconnects one clean, inactive, byte-preserved non-default worktree
  using Git's non-forced `worktree repair`.
- **Initialize default branch** creates an absent local actual-default ref at the captured fetched
  commit with a zero-old-OID `update-ref` comparison-and-swap after a final empty-claim check.

A stale or missing local `origin/HEAD` gets an explanation that the live remote HEAD remains
authoritative and no repair is needed. Every other ambiguous, dirty, active, unsafe, default,
detached, ahead, diverged, or changed state remains a refusal; there is no generic Repair.
Maintenance operations retain Body 1's fresh digest, admission, lock, hook, one-attempt,
postflight, and truthful warning/Needs Attention boundaries.

Cards separately show feature-work purpose and activity, then preview Worktree versus Branch
removal recommendation, recovery/override consequence, permission, and dependencies. These are
advisory and never grant permission. Body 2 performs no cleanup, retention, branch deletion,
remote mutation, AWA mutation, or removal scheduling.

## ShadowSync v2 — Body 1

The selection window groups every discovered clone and verified worktree beneath one
`owner/repository` card. A private `repository-authorities.json` record identifies the canonical
clone; the app offers one bounded confirmation panel for unambiguous first-run choices and an
in-card chooser when multiple writable clones exist. Selecting Fast-forward never grants this
authority.

The remote default comes only from bounded `git ls-remote --symref origin HEAD`; there is no
hard-coded `main` fallback. At execution the app fetches only that branch, captures the exact
reported OID, recomputes Equal/Behind/Ahead/Diverged counts, and updates only when exactly one
verified clean worktree has the default branch checked out and is Behind. That worktree may be the
primary or a linked/external worktree. Unrelated dirty, detached, Cursor-managed, or AWA-managed
feature worktrees remain card context and do not block the target.

The update is exactly `merge --ff-only --no-overwrite-ignore --no-autostash <captured-oid>` under
the common-directory lock with immediate claim/ref/config/policy preflight and postflight. Equal is
a verified no-op; Ahead, Diverged, unknown/duplicate claims, dirty/hidden target state, or drift
refuse without branch mutation. Git invokes applicable hooks normally; marker files alone do not
block, while an actual veto or residue is scoped to that operation. Ref-only update, Initialize,
Repair, PR/purpose inventory, and Cleanup remain outside Body 1.

Reference copies stay collapsed and read-only, repository-owned workflows stay protected,
`chaos-scheduler` remains permanent no-touch, and `~/dev` itself is writable only when explicitly
authorized and otherwise eligible. Saved v1 reports open read-only as
**Legacy run — clone-based model**.

## Retained v1/Milestone 6 foundation

Body 1 retains the proven low-level safe-Git, ownership, cancellation, takeover, recovery, and
logging machinery. The detailed bullets below also document the archived clone-based compatibility
path and its tests; where a clone-wide eligibility rule conflicts with the Body 1 contract above,
the repository-card contract is the current production behavior.

- every new selection scans the effective account's descriptor-canonical `~/dev`, evaluates the
  umbrella separately, prunes dot-prefixed implementation directories and the existing exact
  generated-tree names before descent, never follows directory symlinks, and stops below each
  nested repository boundary;
- a strict adapter reads the existing host worktree policy and baseline classifier declarations as
  bounded data. Safety path, read-only/reference, and owner/repository exclusions produce visible
  disabled rows and run no Git commands. An optional generic `artifact_paths` exact/glob class
  omits authoritative non-operator trees before repository inspection or Git; malformed,
  overlapping, escaping, unreadable, or unsupported policy remains fail-closed as
  **Repository Safety Policy Unavailable**;
- `.git` directories and linked-worktree `.git` files are resolved through no-follow metadata,
  deduplicated by common-directory device/inode identity, and retain registered linked-worktree
  topology. A physical primary beneath `~/dev` remains eligible when fully registered feature or
  detached worktrees exist beneath the effective account's physical `~/.cursor/worktrees` root.
  Every path component and both sides of each Git registration are owner-checked and revalidated;
  `main` in a linked worktree, any other external root, worktree config, a missing or symlinked
  worktree, and malformed or mismatched topology block the primary;
- the exact owner-managed pre-commit dispatcher is derived from
  `~/dev/_ops/bin/install-identity-guard.sh` and accepted by byte identity. Marker lookalikes,
  byte drift, arbitrary executable hooks, chained `pre-commit.local`, Husky, Lefthook, and the
  foreign pre-commit framework remain blocked, and discovery never executes hooks;
- valid credential-free GitHub SSH and HTTPS origins remain eligible, including policy-permitted
  third-party repositories. Effective URL rewrites and transport-command configuration are still
  revalidated through the existing non-network pre-fetch gate;
- the bounded repository-config reader accepts one ordinary local `origin` section and refuses
  includes, multiple origins, `.git/config.worktree`, `extensions.worktreeConfig`, custom
  worktrees, custom upload-pack, object alternates,
  replacements, grafts, and unknown shapes;
- one same-executable worker processes the confirmed rows serially; its direct Git supervisor enters the
  already-open worktree descriptor, revalidates metadata, and alone holds the inherited operation
  lease while Apple Git runs—Git, hooks, helpers, and filters do not inherit that descriptor;
- only the active system config source reported by `/usr/bin/git`, followed by normal global
  sources in precedence order, is copied into one private mode-0600 snapshot inside a fresh
  owner-only mode-0700 `/private/tmp` directory; both path components carry owner-immutable flags,
  and the file carries a nonblocking exclusive lock. Local configuration remains live and bound by
  SHA-256 plus file identity/size/mtime checks before and after every command, so configured
  hooks/helpers/filters/fsmonitor are retained without duplicate local entries;
- dirty, busy, detached, non-main, linked-main, hidden-index, replacement/graft, missing-ref,
  removed, retargeted, and identity/config/topology-drift states fail closed without repair. The
  safely identifiable local states are disabled before selection and revalidated before every
  runtime boundary; no blocked row fetches. An update proceeds only for a clean primary attached
  to `main`, and the utility never switches either checkout;
- each fetch records the remote-tracking ref before and after, then freezes exactly one
  porcelain-reported target. Equal, ahead, diverged, and behind histories resolve independently;
  only behind may run the exact FF-only/no-overwrite/no-autostash update, followed by identity,
  ref, branch, and cleanliness postflight;
- authentication, DNS, transport, timeout, and other fetch failures retain stable reason fields and
  do not stop later rows. Local commands have a five-second bound and fetch has a 120-second bound;
- ignored-file collisions and hook-created residue are preserved. A verified completed ref with
  residue is reported as a warning; uncertain update poststate requires attention and is never
  repaired or rolled back;
- one close-on-exec launcher lock owns one private same-UID control socket. A duplicate launch
  validates the incumbent's user, generation, process birth, executable, and socket challenge,
  then asks the incumbent to present the active run; socket names and persisted PID/PGID values
  never authorize a signal;
- worker admission uses a parent-published start gate after process-group identity capture. Cancel
  first uses the typed channel, waits two seconds, and only then revalidates the same owned
  generation/group before TERM; after five seconds it revalidates again before KILL and allows two
  more seconds for reaping;
- only a duplicated operation-lease descriptor reaches direct Git. If host and worker disappear
  while Git survives, that lease blocks both a new run and lifecycle mutation; the utility reports
  the prior operation, sends no unverified signal, and waits for kernel-observed release;
- each admitted child identity is published to the host before its exec gate opens, so a surviving
  host drains that reverified group if its worker exits; channel EOF uses the same cancellation
  path. Completed rows remain terminal, active rows are
  reconstructed by descriptor-safe read-only ref postflight as updated-before-cancellation,
  cancelled-without-update, or needs-attention, and pending rows become cancelled-pending;
- the latest log records run intent, repository checkpoints, controls, terminal results, and worker
  exit in one private line-framed stream. Subprocess/newline content remains escaped data, seeded
  credentials are redacted, a partial tail is ignored, and unsafe file identity preserves the
  previous bytes;
- the AppKit host provides a scrollable zero-default list, all/clear/subset selection, exact
  multi-row review confirmation, stable ordered native progress/report rows, text plus semantic
  symbols, per-row timing, Open Log, Close Run, Quit ShadowSync, and the fixed
  `Control-Option-Command-M` Carbon shortcut. Safely identified durable repositories that cannot
  update remain visible as disabled rows with one plain-English reason and an eligible/blocked
  count; disabled rows never enter Select All, confirmation, admission, or a worker payload;
- a repository leads with canonical GitHub `owner/repository` identity only after validation.
  When origin or config cannot be validated, its disabled row uses a bounded local basename and
  never invents repository identity. Every newly discovered row includes its compact
  `~/dev`-relative location; selection also labels cached local `origin/main` relation as
  informational—not current GitHub truth. Full local paths are not repository names. Legacy
  records may use a validated full path only as subordinate context; an unsafe or still-ambiguous
  location blocks presentation;
- menu/shortcut routes reuse and foreground the current selection/run/report, secure log opening
  revalidates the current owner-only regular single-link bounded file immediately before opening,
  and keyboard order and adaptive semantic layout remain usable without a pointer; and
- the source-bound lifecycle implementation can install, reconcile, repair, diagnose, roll back,
  and remove the fixed user app and LaunchAgent. Live invocation remains release-gated: before
  explicit M6-T4 approval, only explicit temporary-root tests may exercise lifecycle writes.

### macOS 26 hidden menu icon

macOS 26 can keep a healthy ShadowSync status item off-screen when its Menu Bar setting is
disabled. The app performs one deferred launch check using only public AppKit state:
`NSStatusItem.isVisible` plus the status button's `NSWindow.screen` and frame intersection with
available `NSScreen` frames. A missing button, window, or screen makes the result inconclusive and
shows nothing. A confirmed hidden item queues one non-modal message for the current or next normal
ShadowSync window; reopening that window does not queue the message again.

If the menu icon is missing, use `⌃⌥⌘M`, then enable it in **System Settings → Menu Bar**. On the
diagnosed host, macOS attributed the item beneath **Cursor**; enabling that entry may also expose
other Cursor menu items. ShadowSync neither reads Control Center state nor changes the setting.
AppKit already assigns this single status item an automatic persistence name. The app does not
replace it with an explicit `autosaveName`: that public API persists position and visibility, but
does not provide a documented independent StatusKit identity, and changing the persistence key
could discard the user's existing visibility preference.

### Operator-authorized accessibility delivery variance (2026-09-06)

The operator descoped accessibility-specific acceptance from v1/M5. Manual VoiceOver speech,
caption, and navigation checks and accessibility sign-off are outside this release gate and cannot
block M5; spoken audio remains **UNOBSERVED**, not passed. Existing AppKit accessibility metadata,
labels, help, and automated diagnostic calculation remain intact. The emitted
`accessibilitySemantics` field remains schema-required, but its boolean value is a nonblocking
diagnostic.

Keyboard navigation and focus, safe Return/Escape defaults, canonical identity/location hierarchy,
shortcut/menu foregrounding, window restoration, and adaptive/bounded layout remain required core
UX/safety gates. Only the explicitly optional largest-text, Dark appearance, and Increase Contrast
UAT variants below are non-gating.

The accepted v1 plan remains unchanged as frozen historical authority because this repository's
governed successor route is unavailable. This operator-authorized delivery variance neither claims
plan conformance nor acts as a governance successor, and it creates no roadmap obligation.

## Milestone 6 lifecycle

The default installer is the standard bootstrap/reconcile entrypoint. Before building, it requires
the canonical `KleinPerkins/skills` origin and durable physical primary checkout on `main`, exact
local `origin/main`, ordinary Git object semantics, a clean tracked and untracked capability scope,
and a committed metadata-lock row recomputed with the canonical lock algorithm. It hashes sorted Git
tree records plus that row, captures the exact commit with `git archive`, verifies every captured
blob and mode against its Git object, embeds the producing revision,
source-input and metadata-contract SHA-256 values, architecture, minimum OS, version, and build mode
in `Info.plist`, then signs the complete staged bundle with timestamping disabled.

Install, update, repair, and removal acquire lifecycle then operation authority before product
mutation. Parent directories remain pinned while no-replace renames promote uniquely named,
fsynced incomplete copies through fixed same-directory incoming/previous slots. Deletion first
quarantines an identity-checked owned target. The
installer drains only a challenge-verified host, unloads only
`com.kleinperkins.dev-main-sync`, verifies the exact six-key LaunchAgent and copied post-sign bundle,
revalidates source identity immediately before promotion, and requires release-bound peer-PID
readiness from the new host. A healthy identical-source
reconcile is a byte/process no-op even when a later Skills commit has the same capability tree.
The registered LaunchAgent uses `RunAtLoad=false`: installation explicitly starts the installed
build once, but an ordinary Mac login does not start ShadowSync. A user can opt in through the
app-menu **Open ShadowSync at Login** setting, backed by the standard macOS Login Items service.
After a clean quit, a manual app launch routes through the exact loaded LaunchAgent and starts its
single managed host; it never admits the manual process itself. Explicit repair of that same
verified loaded-but-stopped installation restarts the job without replacing app or plist bytes.
Manual routing and the stopped-job restart path still fail closed for an absent label, query
failure, executable drift, or invalid launchd PID.
Ordinary reconcile refuses an unhealthy or signature-tampered target; explicit `--repair` is the
only replacement path after strict owner/path/type checks. Pre-commit failures restore the complete
prior app/plist/job. Once readiness commits N+1, cleanup failure leaves recoverable N+1 residue and
never rolls back to mixed N/N+1.

Direct doctor uses read-only opens to verify all transaction slots, fixed app, signature-sealed
release metadata, exact LaunchAgent, every owner-only coordination lock, the exact state-entry
allowlist, typed loaded-label program/PID, and release-bound owner/socket/readiness coherence.
Verified removal unloads only the owned label, removes owned app/plist/socket/registration and all
four lock names, and preserves only `latest.log`. The retained log is acquired before any
coordination lock and exclusively gates lock-namespace retirement/recreation, so an interrupted
uninstall cannot split old and replacement lock authority. Unknown, aliased, special,
multi-linked, contended, or unverifiable state refuses without authorizing a signal or deletion.

This is accidental/race integrity for one local user account. Ad-hoc signing detects ordinary
post-build modification; it is not independent publisher identity, and deliberate modification
followed by re-signing by the same account is outside this threat boundary. No Developer ID,
remote signer, receipt, updater, service, or network trust is claimed.

`scripts/verify-m6.sh` creates one fresh owner-only `/private/tmp/dev-main-sync-m6.*` fixture,
builds two independent archive/object/scratch releases plus testing bundles with Command Line Tools,
and exercises install, same-source
no-op across unrelated revisions, N→failed-N+1 rollback cuts, launch failure, doctor, and removal
through an injected launchd controller and a separate isolated installed-host process that owns the
real launcher lock, control socket, peer identity, and readiness exchange. Crash fixtures persist
and reconstruct that simulated launchd process state, assert phase-specific admission outcomes,
and reap owned helpers on every timeout or top-level cleanup. It never calls
`/bin/launchctl`, snapshots live
product state before/after, preserves the production log/socket/locks byte-for-byte, and deletes
the explicit test root.

The transport test seam and temporary state-root controls compile only when
`SHADOW_SYNC_TESTING` is defined. A testing bundle refuses normal launch before `NSApplication`
unless it receives a validated inherited isolated test channel. The production bundle has none
of those options or symbols.

## Command Line Tools test runner

The selected Command Line Tools expose neither XCTest nor Swift Testing on Swift's default import
path, so package sources cannot register normal tests without unsupported private framework
imports. Literal default `swift test` succeeds only as a compile/package check: SwiftPM
synthesizes a runner but runs zero tests. This was confirmed with `xcrun swiftc -typecheck`:
both `import XCTest` and `import Testing` fail under the selected Command Line Tools. No
unsupported private framework is imported, and the zero-test result is never presented as
runtime coverage.

`scripts/verify-m1.sh` is the canonical M1 entrypoint. It runs literal `swift test` as the
compile/package gate, the no-dependency executable runtime harness, and the native staged-app
E2E. The harness covers the closed command/environment policy, metadata/config/graph races,
ordinary-object refusal, child-start admission, run/lifecycle/operation locks, inherited lease
survival, secret-free bounded argv metadata, separate machine stdout/stderr, strict fetch
porcelain parsing, hardlinked and framed logs, redaction, partial-tail reconstruction, and channel-EOF
  process-group cleanup. Its M3 cases add the relationship/refusal matrix, pre-fetch non-main and
linked-main refusals, missing refs, runtime policy drift, fetch/update residue, ignored collisions,
failure-reason continuation, exact command audit, timeout defaults, monotonic timing, and complete
  result serialization. M4 adds process-birth/generation signal proof, exact escalation-bound
  state tests, launcher/socket challenge and stale-socket refusal, surviving-lease blocking,
  responsive/stubborn group reaping, deterministic interrupted reconstruction, and intent/control
  log framing. None of those test-only entry points is linked into the production app.

`scripts/m1-core-tests.sh --practical-only` runs the focused repository visibility, artifact
policy, local-state preselection, exact rediscovery/admission, shared transaction inspection, and
post-review race cases, then prints a read-only live inventory projection. It does not change the
live host policy or installed app.

`scripts/verify-m5.sh` is the focused M5 automated entrypoint. It exercises exact copy and row
states, menu/shortcut lifecycle routing, report reopening, secure log-open refusals,
keyboard-safe alert defaults, canonical AppKit row and selection metadata (non-release-blocking
regression coverage), adaptive native layout, and mixed/cancelled reports in an isolated testing
bundle. It
also emits every raw sample plus p95 and maximum latency for three 60-second trials with 100 rows
and one event every 25 ms; each trial requires ordered, complete rendering, p95 at most 250 ms,
while maximum latency remains a non-gating diagnostic. This automated evidence does not replace
target-Mac UAT.

`scripts/verify-m5.sh --practical-only` builds the same isolated testing bundle but runs only the
disabled-row reason, eligible/blocked count, Select All, review-payload, and keyboard-focus
regressions for practical repository discovery changes. It also locks the Beta v0.1 menu labels,
native shortcut key equivalent, menu/shortcut routing equivalence, readable chooser geometry,
both-axis resizing, and zoom/full-screen capability. It does not run the full M5 or latency matrix.

`scripts/beta-v0.1-native-smoke.sh --output-dir ABSOLUTE_FRESH_PATH` builds an isolated testing
host, then uses macOS System Events accessibility automation and `screencapture` to preserve the
actual chooser at initial, horizontal, both-axis, full-screen, and restored sizes. It changes no
installed app or repository and requires accessibility permission for the invoking terminal.

`scripts/beta-v0.2-native-smoke.sh --output-dir ABSOLUTE_FRESH_PATH` applies the same native
automation to the live process-free catalog projection. It verifies origin consolidation,
canonical-root presentation and Change control, collapsed non-selectable sections, and retained
window behavior without running Git or mutating repositories.

`scripts/verify-beta-v0.2.sh` is the narrow model/regression gate for origin normalization,
linked-worktree suppression, canonical-root persistence, origin-bound defaults, status sections,
missing metadata, unchanged refresh continuation, and changed-root reconciliation.

`scripts/verify-beta-v0.5.sh` covers the manual-start registration, regular macOS app presence,
menu-bar pull-request glyph, terminal-report Quit behavior, ordinary large-index inventory,
stale-registration Fast-forward/Repair admission, cleanup grouping, and its frozen release checks.

`scripts/verify-beta-v0.6.sh` is the focused `0.6.0 (11)` corrective gate. It covers checked-out
unknown-relation execution, exact default-claimant admission, linked-worktree preservation,
same-session delta hydration, cleanup-inspection gating, terminal/new-run and independent-history
ownership, stable grouped result rows, deterministic historical metadata, bounded redacted
diagnostics, and pre-v0.6 v2-log decoding. All fixtures are isolated under `/private/tmp`; this
gate does not accept operator UAT or mutate live repositories.

`scripts/verify-beta-v0.7.sh` is the focused `0.7.0 (12)` corrective gate. It proves incremental
bounded Live Log projection, one reusable redaction-expression set, coalesced event/UI evidence,
collapsed-log laziness, neutral unavailable Repair copy with technical diagnostics, stable
repository/action hierarchy geometry and identities, and current release metadata. Fixtures remain
isolated under `/private/tmp`; the gate neither installs nor mutates live repositories.

`scripts/verify-beta-v0.8.sh` is the focused `0.8.0 (13)` corrective gate. It proves the shared
32 MiB complete-inventory bound across inspection, Fast-forward, Repair, and preservation; typed
fail-closed overflow diagnostics; conservative stale-remote relation copy; dynamic cleanup-panel
appearance; local wall-clock completion metadata; retained linear Live Log behavior; and current
release metadata. Fixtures remain isolated under `/private/tmp`; the gate neither installs nor
mutates live repositories.

`scripts/verify-beta-v0.9.sh` is the focused `0.9.0 (14)` corrective gate. It proves bounded bulk
local relation discovery, at-most-four current-repository read-only PR children, adaptive
fail-closed partial evidence, retained single/all inspection progress, contained branch/worktree
subcards, long-identity layout constraints, unchanged selected-batch hierarchy, and current release
metadata. AWA-shaped 21-worktree/75-branch and skills-shaped 20-worktree/84-branch fixtures remain
isolated under `/private/tmp`; the gate neither installs nor mutates live repositories.

## Legacy Milestone 5 target-Mac UAT

This archived v1 checklist is retained as compatibility evidence; it is not the v2 Body 1 operator
flow.

Use the reviewed production build on the target Mac without installing or loading a LaunchAgent.
Use only repositories approved for this test. Record the Mac/OS/build identity, tester, date,
result, and notes for each required item; the M5 gate remains open until Laurence or a delegate
records a pass for those core items.

1. Open **Update local main branches** with `⌃⌥⌘M`; press the shortcut again and verify the same
   window is foregrounded, not duplicated. With the keyboard only, traverse every repository and
   **Select All**, **Clear All**, **Cancel**, and **Review Selection…** in logical order. Verify
   each row shows canonical `owner/repository` and eligibility; duplicate-origin checkouts also
   show their compact `~/dev` location.
2. At zero selection, verify **Review Selection…** is disabled and Return starts nothing. Select
   one and then several rows with the keyboard. In confirmation, verify each canonical GitHub
   identity appears first with its compact `~/dev`-relative location beneath it. When compact
   location cannot safely distinguish duplicate-origin checkouts, a validated full local path may
   appear only as subordinate fallback context. Return chooses safe **Back**, Escape chooses
   **Cancel**, and update starts only after explicitly choosing **Start Update**.
3. During a run, verify every selected row remains visible and text status is readable; symbols
   remain distinguishable without color. Hide progress and use both the menu and `⌃⌥⌘M` from
   another frontmost app to restore that same run. In stop/takeover prompts, Return and Escape
   preserve the active run; stop only through the explicit destructive action.
4. Complete one normal or mixed run and one cancellation. Verify the exact summary, ordered rows,
   fetched/updated values, start/end/duration details, **Open Log**, and current/last-report
   reopening. Close with **Close Run**, verify the status item and latest log remain, then reopen
   **Show Last Report** and confirm its evidence is unchanged. The red window close control hides
   a run/report for later restoration; only **Close Run** releases that presentation.
5. Resize each selection, progress, and report window to its minimum and larger sizes. Verify the
   adaptive/bounded layout remains usable: long names wrap or scroll, controls stay reachable,
   keyboard focus stays visible, and no workflow meaning depends on color. This core check is
   required. Optionally (non-gating), repeat it at the largest practical system text size, in Dark
   appearance, and with Increase Contrast enabled.
6. Give another app a real global `⌃⌥⌘M` binding before launching the utility. Verify
   **Keyboard Shortcut Unavailable** appears while every menu route still works. Remove the
   temporary binding and record which app supplied the collision.
7. While a run is active, choose **Quit ShadowSync**. Verify Return/Escape keep the run, then explicitly
   confirm stop-and-quit and verify the owned run drains before the status item disappears. Launch
   again manually, finish or close its report, choose **Quit ShadowSync**, and verify it stays gone
   until a manual launch. If **Open at Login** was explicitly enabled for the UAT account, verify
   that opt-in separately. Preserve the latest log for evidence.

For deterministic mixed warning-and-cancellation composition, use disposable UAT clones only.
Create at least eight clean, independent clones of the same approved public origin under the test
area in `~/dev`; name the intended dirty checkout so its validated path sorts first (for example
`00-dirty-first`). Open selection, select those clones in displayed order, and stop at the review
confirmation. Before choosing **Start Update**, add one harmless untracked fixture file to
`00-dirty-first` from a separate Terminal. Execution-time revalidation must render that first row
as `SKIPPED_DIRTY`. After observing it, choose **Cancel Run** so later fixture rows become cancelled.
Remove the disposable clones after recording evidence. Do not perform this recipe on a real working
repository, and do not edit stored reports or production state to manufacture the result.

## Git contract

Every Git command is selected from a closed enum-like argument policy and runs as
`/usr/bin/git --no-replace-objects ...` with a closed environment and `/dev/null` standard input.
Nominally local graph and worktree queries also require `--no-lazy-fetch`.
The transaction:

1. proves one unchanged credential-free GitHub origin, exact effective transport, effective Git
   top-level, and stable bounded config contributors; the child repeats those checks immediately
   before fetch/update and rejects custom transport or contributor drift;
2. requires one explicitly authorized canonical clone and exactly one owner-controlled, verified,
   clean worktree claiming the remotely resolved default branch, with no hidden index state or
   active operation on that target;
3. fetches with `--porcelain --verbose --no-write-fetch-head --no-tags --no-prune
   --no-recurse-submodules --no-auto-maintenance`, captures exactly one OID for the resolved
   `refs/remotes/origin/<default>`, and never uses local `origin/HEAD` or a fallback branch;
4. revalidates repository identity, authority, policy, origin, complete branch claims, target
   worktree, cleanliness, config, and the expected local commit after fetch; unrelated feature
   worktrees remain context;
5. treats equality as a no-op and preserves ahead or diverged histories; and
6. updates only with
   `merge --ff-only --no-overwrite-ignore --no-autostash <captured-object-id>`, followed by
   postflight verification.

There is no reset, pull, rebase, stash, clean, checkout, switch, push, force update, or history
rewrite path.

Apple Git operational commands consume the retained snapshot path through `GIT_CONFIG_GLOBAL`;
`GIT_CONFIG` is deliberately absent so the digest-bound live `.git/config` remains visible.
The supervisor retains open file and directory descriptors and validates both descriptor/path
identities, SHA-256, size, mode, immutable flags, and lock before and after each command.
Authenticated normal cleanup clears the flags before unlinking. If the worker dies, the supervising
trampoline cleans after Git exits; a later run descriptor-relatively recovers only a validated,
owned, unlocked stale snapshot and refuses questionable entries. These controls harden accidental
single-user races; M1 does not claim to defeat a hostile same-user process. It also closes known Git
override channels, uses `GIT_GRAFT_FILE=/dev/null` and no-replace mode, and fails on observed
contributor/graph drift.

## Safe local commands

These commands neither install nor load the utility:

```sh
./install.sh --check
./scripts/v3-preflight-acceptance.sh
./scripts/v2-body1-acceptance.sh
./scripts/v2-body2-acceptance.sh
./scripts/v2-body4-acceptance.sh
./scripts/verify-m1.sh
./scripts/verify-m5.sh
./scripts/verify-m6.sh
./scripts/beta-v0.1-native-smoke.sh \
  --output-dir /private/tmp/shadowsync-native-smoke
./scripts/beta-v0.2-native-smoke.sh \
  --output-dir /private/tmp/shadowsync-v02-native-smoke
./scripts/verify-beta-v0.2.sh
./scripts/verify-beta-v0.5.sh
./scripts/verify-beta-v0.6.sh
./scripts/verify-beta-v0.7.sh
```

Explicit temporary staging:

```sh
./install.sh --m1-stage \
  --test-root /private/tmp/dev-main-sync-stage \
  --scratch-path /private/tmp/dev-main-sync-stage/swift
./install.sh --doctor --test-root /private/tmp/dev-main-sync-stage
```

No-argument `install.sh`, `--apply`, `--repair`, and `--uninstall` are live fixed-root lifecycle
commands. Do not invoke them until the M6-T4 release gate has fresh explicit operator approval.
`install.sh --doctor` is strictly read-only: canonical source classifies an absent or removed
installation directly, and source-attests a present bundle before its lifecycle doctor may run.
`install.sh --source-identity` performs only the clean canonical-source/provenance preflight.

The test root, scratch path, output directory, and every staged descendant must be fresh,
owner-only physical paths below `/private/tmp`; existing or symlinked destinations are refused.
The native E2E stages (but never bootstraps) a testing app and LaunchAgent, drives the actual
status host through its inherited test channel, and exercises only local bare remotes. It proves
selection/review/confirmation/progress/report/close/quit, worker-crash terminal recovery and
lease survival, exact OIDs and ordered phases, behind update, equal no-merge, config/transport/
replacement/graft/alternate refusal, redaction, closed-environment sentinels, private logging,
an exact production-bundle path/type/mode allowlist, production test-seam absence, bootstrap
dry-run recognition without installer invocation, and recursive live-state plus bounded
`~/dev` Git-control snapshots before deleting the fixture. Every staged app process and its
descendants run under an enforced `sandbox-exec` network denial; the credential-free local file
mapping remains functional inside that sandbox.
