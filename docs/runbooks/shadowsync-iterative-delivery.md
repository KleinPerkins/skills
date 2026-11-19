# ShadowSync iterative delivery

## Current stage and scope

**Stage:** Beta v0.9 bounded inspection correction installed; operator UAT remains open
**Scope:** Exercise optional-inspection scaling, retained progress, and RLCC candidate
hierarchy/alignment on the installed v0.9 surface. All cleanup/removal permission, recovery,
identity, mutation, selected-batch, history, report, and Quit behavior remains unchanged and in
operator UAT.

Every future ShadowSync task must state the current release stage and in-scope workflows before
changing code. Beta work stops once those workflows are meaningfully testable, essential failures
are handled, and there is no credible data-loss, credential-exposure, or unsafe-destructive risk.
Non-blocking defects are recorded below rather than expanded into broad hardening.

## Release provenance

A beta may be presented as **released** only when its installed build names an exact revision that
is committed, pushed, fully merged into the canonical target branch, and verified there. Dirty
worktree bytes, unpushed commits, feature-branch heads, proposed changes, and open-PR changes are
test candidates only; they cannot be part of a released beta. Record the exact merged source
revision and its pull request when applicable.

- **Candidate status:** Beta v0.7 marketing version `0.7.0`, build `12` is authorized on branch
  `fix/shadowsync-beta-v0.7-build12`, created from clean exact `origin/main`
  `c95c4009226b8385d8bf222a0da31f14de1817f2`. The accepted v0.7 execution plan v1 has SHA-256
  `dc0af24fbbad499e583dbc98cef3e97eaca25048301fe9ba2ed354c18ca6f49f`; inherited ADR 0005
  remains SHA-256 `666cc99b0612c936ed8910d78a4a03c69da620b0b371c1f69405e1c7cab6c8ea`.
  Candidate bytes are not released and must not replace the installed v0.6 app before a
  controller-owned exact-head merge and separate exact-main installation.
- **Release status:** Beta v0.6 build 11 was merged from implementation head
  `7dd9bb721c6e32c6e9a1bdab7198d303487099b3` by
  [PR #217](https://github.com/KleinPerkins/skills/pull/217) as exact canonical source revision
  `ab3fc273e22bf91bbe4ee325e77958dfe1f89abe`; the merged and implementation trees were
  byte-identical. Exact-main release gates passed, and the governed repair path installed
  `0.6.0 (11)` after ordinary reconcile safely refused the cleanly stopped prior host. Installed
  doctor, signature, bundle identity, source revision/input digest, metadata-contract digest,
  LaunchAgent readiness, and visible managed-host checks passed. Native smoke visually confirmed a
  readable chooser; an independent `ShadowSync · Last report (read-only)` window with historical
  timing, repository/action totals, and stable left-aligned repository/action rows; Start New Run
  returning to the chooser; ordinary Quit/drain with exit status zero; and healthy relaunch to the
  chooser. Operator UAT remains open.
- **Prior release status:** Beta v0.5 build 9 was merged from
  `8325d28955bce96afd6992203005dec101750d98` by
  [PR #214](https://github.com/KleinPerkins/skills/pull/214) and installed from exact `main`.
  Its installed smoke passed release identity, signature, `RunAtLoad=false`, managed-host
  readiness, and regular visible application-process checks. It also exposed one release-blocking
  omission: a fresh `SMAppService.mainApp` state reported `.notFound`, and the app disabled
  **Open ShadowSync at Login** instead of allowing the first registration attempt. Beta v0.4
  build 8 was merged from
  `7f445b88bacf6197275469b7474d279f68b8133f` by
  [PR #213](https://github.com/KleinPerkins/skills/pull/213), installed, and entered UAT. Its first
  two feedback rounds established the Beta v0.5 corrections below. Earlier, Beta v0.4 build 7 was
  merged from
  `6eb0492bdde0c3cd53c407b55ec08defa4c88da8` by
  [PR #212](https://github.com/KleinPerkins/skills/pull/212); its installed smoke found that
  closing a recovered completed-batch report did not carry that window's frame/screen anchor into
  the next run. Earlier, Beta v0.3 build 6 was released from
  `8398fe08c4b40cbba5983beaa39a6bde6f6b80a7` by
  [PR #211](https://github.com/KleinPerkins/skills/pull/211), then failed expanded lifecycle-center
  UAT because exhaustive cleanup enrichment suppressed top-level Fast-forward eligibility.
  Earlier, Beta v0.2 build 4 was released from
  `7c8c2e9f4785bde6b8cd3212c93ab0351e1e2cb0` by
  [PR #209](https://github.com/KleinPerkins/skills/pull/209), then failed expanded operator UAT.
  Beta v0.3 build 5 merged from `93ada3ddd6438264b289e39f869ce771542223b0` by
  [PR #210](https://github.com/KleinPerkins/skills/pull/210), but its installed smoke found the
  post-cancel Continue blocker below. Build 6 is the authorized minimal corrective candidate.
- **Corrective recut:** Explicitly authorized in the existing sanctioned worktree with one owner.
- **v0.2 build 3:** [PR #208](https://github.com/KleinPerkins/skills/pull/208), merged and installed
  from `f90f910c9bb189068ed97be8fe9963f0724edfbf`.
- **v0.5 build 10 identity:** Marketing version `0.5.0`, build `10`; this corrective recut
  preserves build 9's authorized startup/app-presence, menu-icon, Quit, Fast-forward-readiness,
  validation, and cleanup-layout changes while repairing first-time Login Item registration.
- **v0.6 build 11 candidate:** Marketing version `0.6.0`, build `11`. The operator authorized the
  corrective implementation on branch `fix/shadowsync-beta-v0.6-build11`, created from the clean
  detached linked-worktree baseline `1674a878e7b0cb38049796e3df232b6f753a0996`, which exactly
  matched `origin/main`. Frozen authority bytes at branch creation were ADR 0005 SHA-256
  `666cc99b0612c936ed8910d78a4a03c69da620b0b371c1f69405e1c7cab6c8ea` and plan v1 SHA-256
  `99fda5c4303ada32e26c50e3cb4e047e7a8e835333876d8f9142b8dd23a13251`. The
  corrective source body and candidate-local gates below are complete. The exact tested head,
  ready PR, controller merge revision, exact-main installation, and installed smoke provenance are
  governed delivery receipts; branch or dirty bytes are not a release.
- **UAT phase:** Open until the operator explicitly states Beta UAT and feedback are complete; no
  requirement acceptance is inferred from continued testing, successful operation, or app use.

## UAT and requirement decisions

Every feedback item remains open until any ambiguity is clarified. Restate the interpreted feedback
in operator language. If it implies a requirement change, recommend one revised requirement with
its user-visible tradeoffs and risks, then obtain explicit operator authorization for that
individual revision before treating it as accepted or implementing it.

Track requirement acceptance independently from general feedback. Use: **not tested**,
**feedback pending clarification**, **change proposed — awaiting authorization**, **accepted**,
**rejected**, or **operator-deferred**. Never infer acceptance from silence, successful automated
tests, general satisfaction, or use of the app.

Engineering completion does not conclude a beta's delivery/UAT phase or authorize movement to
another beta, MVP, or post-MVP. Only the operator's explicit statement that UAT and feedback for
this phase are complete can start phase closeout. Before acting on that signal, present every
remaining untested or unaccepted workflow and ask the operator to test, accept, reject, or
explicitly defer each. Preserve explicit deferrals across versions and sessions.

Beta feedback that changes a requirement, design, UX, priority, or acceptance decision must update
the matching feedback entry and reconcile any affected deferred entry in the same change. Moving
to MVP hardening requires explicit operator approval and is limited to the agreed P0/P1 risks; it
does not authorize general refactoring, exhaustive regressions, polish, performance work, or
production hardening.

## Failed-candidate UAT and authorized corrections

### UAT-01 — Menu-bar icon appearance

- **Interpreted operator feedback:** “The menu-bar icon looks right.”
- **Status:** Accepted for the failed `0.1.0 (1)` candidate.
- **Requirement impact:** None; preserve the current icon appearance.

### UAT-02 — Basic menu

- **Interpreted operator feedback:** “The menu opens and its basic items are understandable, but
  Start New Run must show ⌃⌥⌘M beside it and Quit Utility must say Quit ShadowSync.”
- **Status:** Partially accepted; both corrections explicitly authorized.
- **Authorized requirement:** Use the native `⌃⌥⌘M` key equivalent on **Start New Run…** and label
  the quit item **Quit ShadowSync**.
- **User-visible tradeoff / risk:** The active-app menu key equivalent and global Carbon shortcut
  must route to the same flow without duplicate windows or duplicate operations.

### UAT-03 — Shortcut invocation

- **Interpreted operator feedback:** “The shortcut opens something, but the resulting window is
  too narrow to understand or use.”
- **Status:** Failed / not accepted; Beta blocker shared with UAT-04.
- **Authorized requirement:** Menu and `⌃⌥⌘M` must open or foreground the same usable native flow.

### UAT-04 — Start New Run window and core flow

- **Interpreted operator feedback:** “Start New Run opens an extremely narrow, unreadable window.
  Horizontal edge dragging and macOS Move & Resize / Fill & Arrange do not fix it, full-screen is
  unavailable, and attempted height resizing behaves incorrectly.”
- **Status:** Failed UAT / Beta blocker. The `0.1.0 (1)` candidate must never be released.
- **Authorized requirement:** Start New Run must be a standard readable native macOS window with a
  sane initial size, responsive content, horizontal and vertical resizing, zoom/full-screen
  support, and safe restoration/clamping of persisted geometry so an invalid narrow frame cannot
  recur.
- **User-visible tradeoff / risk:** Invalid or off-screen saved geometry may be corrected to the
  minimum readable frame; valid user-selected size and position remain restorable.

### UAT-05 — Smoke and release gates

- **Interpreted operator feedback:** “Harnesses were not enough; the installed UI and complete
  happy path must be visibly exercised before release.”
- **Status:** Prior smoke gate rejected; replacement requirements explicitly authorized.
- **Authorized requirement:** Use native macOS UI automation plus screenshots or compact video for
  native surfaces; use Playwright only for web surfaces. Verify installed launch, menu, shortcut,
  readable/resizable/full-screen Start New Run, chooser/defaults/canonical roots, controlled safe
  sync, refusals/cancel, reports/logs, and ordinary Quit.
- **Release requirement:** One sanctioned worktree/branch and owner; normal PR/check/review/merge;
  synchronize local `main` with `origin/main`; then build and install from that exact merged commit.

### Failed-candidate visual evidence

Five historical PNGs and a recording remain in the retained private original. This clean
successor omits those captures because their backgrounds contain private chat and workspace
content. Their filenames, hashes, and local paths are retained only in the private disposition
receipt; they are not successor assets or evidence available from this source tree.

### Corrective pre-merge visual evidence

Native System Events automation exercised initial presentation, independent horizontal and
vertical resizing, native full-screen entry, and restored geometry. The five captures were
visually inspected; text and controls remain readable, and no narrow-frame recurrence appears.
The repeatable command is `scripts/beta-v0.1-native-smoke.sh`.

- `assets/shadowsync-beta-v0.1-recut/premerge/01-initial.png` —
  `5cb51641c1b8de647f500055063bfb75d51b4db5fc10d4bbf890ac8cf472f0dc`
- `assets/shadowsync-beta-v0.1-recut/premerge/02-horizontal.png` —
  `a1ce34a26cf354c05b6574f671958b7fb26efa6c0de7dfe915d6cb1080187870`
- `assets/shadowsync-beta-v0.1-recut/premerge/03-both-axes.png` —
  `4aedccf22a339df32acbf4f13d2fd9928b0eecb4dab9bf10bde83e506a4977ec`
- `assets/shadowsync-beta-v0.1-recut/premerge/04-full-screen.png` —
  `b5fa8552419e856ebe8c784e439c6990a6b2ddba07ee0de85623dd3145f2e717`
- `assets/shadowsync-beta-v0.1-recut/premerge/05-restored.png` —
  `10dc02473e44cb328b6333584d0d53c360373aa7c19d715edf5ed4ccb9096bd9`
- `assets/shadowsync-beta-v0.1-recut/premerge/evidence.json` —
  `7e6009f261396d853dc200b14832e97c499b0f4fa05dabc7d30c5d7622573ec6`

### Corrective pre-merge verification

- `scripts/verify-m5.sh --practical-only`: PASS — menu labels/key equivalent, menu/shortcut route
  equivalence, invalid-frame recovery, both-axis resizing, zoom/full-screen capability, and
  practical chooser behavior.
- `scripts/beta-v0.1-native-smoke.sh`: PASS — five actual native captures, visually inspected.
- `scripts/m1-native-e2e.sh`: PASS — AppKit flow, behind fast-forward, Equal no-op, refusal matrix,
  report/log/close/quit path, production symbol isolation, and unchanged live state.
- `scripts/v4-preflight-acceptance.sh`: PASS — DM4-T01–T12, packaging, attestation, and migration.
- `.github/scripts/verify-skills.sh`: PASS — repository gate including v3 runtime acceptance.
- `doc-warden check`: pre-existing overall DRIFT remains in three untouched plan records; changed
  agent instruction and current ShadowSync plan/ADR authorities are conformant.
- **Transient broad-gate result:** A later repository-gate run classified one isolated fixture
  `git for-each-ref` as timed out even though Git exited `0` and returned the expected refs. This
  occurred after sustained compile load, did not reproduce in the focused native visual or core
  happy-path checks, and indicates no data, credential, or destructive risk. The operator directed
  that expensive broad reruns stop; an in-progress retry was terminated and this result is a
  disclosed Beta v0.1 non-blocker. Required remote merge checks remain authoritative.
- **Merged-install blocker:** The first exact-main install correctly exposed that build-2 source
  rejected the installed build-1 metadata before migration. The minimum compatibility fix accepts
  prior positive build numbers up to the current build for prior-state verification, while the
  source bundle remains required to equal the current build. The focused M6 release/lifecycle check
  passed; final merged installation remains open.

## Beta v0.2 origin-centric chooser

The second v0.1 blocker was one shared model mismatch: the process-free catalog rendered physical
checkout rows, while Continue and the defaults document required unique logical repository IDs.
Selecting two `kp-mcp` checkout rows therefore produced both the self-generated
**Selected repositories changed** loop and `invalidDocument` on Save. Beta v0.2 moves that
uniqueness boundary into the catalog/UI instead of asking the operator to repair it.

### Build-3 installed smoke and build-4 authorization

- **Save/reload:** PASS — `KleinPerkins/dev` saved without `invalidDocument` and restored checked.
- **Continue:** FAILED — fresh selected hydration rejected the persisted `KleinPerkins/dev`
  authority.
- **Diagnosis:** The canonical path, root inode, `.git` inode, owner and normalized origin still
  matched; only APFS device numbers changed after restart (`16777231` → `16777234`).
- **Classification:** Reboot-stale cross-session evidence and an overly strict durable identity
  comparison, not an unsafe repository.
- **Operator authorization:** For a selected record only, automatically CAS-refresh device-only
  drift after fresh no-follow path, inode, owner, origin, policy and topology validation. Any other
  mismatch or race fails closed for that origin and uses the existing Change flow.
- **Build-4 focused regression:** PASS — device-only drift refreshed; path/root inode/common-dir
  inode/origin/policy/topology mismatches rejected; stale CAS identity refused.
- **Build-4 status:** Implemented — awaiting governed delivery and one installed Continue retest.
  UAT remains open.

### Authorized requirements and candidate status

- **Origin-centric inventory:** Implemented — one row per normalized origin identity.
- **Canonical primary path:** Implemented — each ordinary row displays
  `owner/repository — canonical path`; linked worktrees are suppressed.
- **`KleinPerkins/dev — ~/dev`:** Implemented as an ordinary writable origin row.
- **Branch independence:** Preserved — the first screen does not inspect or gate on current branch.
- **Independent primary clones:** Implemented — unresolved origins appear under
  **Canonical root required** with primary-root alternatives; only a selected unresolved origin
  blocks Continue.
- **Canonical mapping:** Implemented in `repository-authorities.json`, independently of checkbox
  defaults, with a **Change…** action for alternatives.
- **Filter defaults:** Implemented by origin identity through **Save as defaults** only; reopen
  resolves the saved origin to its current canonical root.
- **Sections:** Implemented — Available, Canonical root required, Unavailable/read-only, Excluded,
  and Protected; non-selectable sections are collapsed.
- **Missing metadata:** Implemented — no usable origin or local remote-default metadata produces
  one non-selectable Unavailable row with a precise reason.
- **Continue/Save blockers:** Fixed in focused tests — UI-generated selections are unique by
  origin, Save creates a valid document and restores it, and Continue emits one entry per origin
  without the self-generated Reload gate.
- **Refresh:** Implemented — unchanged selected origin/canonical mappings continue automatically;
  material selected-row changes refresh the chooser, preserve unaffected choices, and explain the
  affected rows.
- **UAT status:** Fixed — awaiting merged installed-app smoke and operator retest.

### Focused evidence

- `--beta-v02-chooser-only`: PASS — origin normalization, linked suppression, independent-clone
  resolution, origin-bound defaults, branch-independent availability, sections, missing metadata,
  and fresh Continue binding.
- `verify-m5.sh --practical-only`: PASS — canonical choice gating/independence, valid Save/reopen,
  Continue callback, collapsed sections, plus retained v0.1 menu/window behavior.
- Native live-catalog smoke: PASS and visually inspected.
- `assets/shadowsync-beta-v0.2/premerge/01-initial.png` —
  `552fadf64ee3f6b95e06ed80946ba6512f929810763129442e12cc5ec4b07d4b`
- `assets/shadowsync-beta-v0.2/premerge/02-horizontal.png` —
  `c0c6d6318b61e408577c7adbedacb91913e95948717f33133bf92e0cb7fc8007`
- `assets/shadowsync-beta-v0.2/premerge/03-both-axes.png` —
  `551b264b67a3b6e0efdd21d220342653e51954ff1c88deaa26dc39ecde733bfa`
- `assets/shadowsync-beta-v0.2/premerge/04-full-screen.png` —
  `5a3969f98c49c8065b6576f882b3168c5a1e97f8290128c6a05271c5a11fe657`
- `assets/shadowsync-beta-v0.2/premerge/05-restored.png` —
  `8f11dd26b74c60e4b12ed4a9c6d7f01b73f5b41e9bf4e50cccd9c9cd2d78a7da`
- `assets/shadowsync-beta-v0.2/premerge/evidence.json` —
  `8e11aabd6372605faceb0b61c6a591be2e9323180e1a11f9e07051e0ad7a84a9`

## Beta v0.3 corrective UAT

The operator concluded Beta v0.2 UAT was blocked and explicitly authorized Beta v0.3. Prior
acceptance remains in force for the menu icon and labels, shortcut, native window geometry,
origin-centric chooser, canonical-root mapping, linked-worktree suppression, status sections,
default persistence, duplicate-selection safety, and device-only authority refresh.

### Authorized feedback and requirements

- **SS-03-01 — Unavailable presentation:** The expanded section repeats the same read-only
  explanation between repositories. Group rows under one broad reason heading; retain only
  genuinely unique row detail. **Status:** Change authorized; awaiting Beta v0.3 retest.
- **SS-03-02 — Save window stability:** Save succeeded, but closed/recreated the chooser and moved
  it across the screen. Save in place; only explicit Reload may rebuild the catalog.
  **Status:** Change authorized; awaiting Beta v0.3 retest.
- **SS-03-03 — Multi-repository hydration:** Two selected origins advanced, while sixteen reached
  a misleading started-only `16 of 16` state and then showed no usable progress. Report completed
  count, current repository, and phase; run one selected hydration pass; bound repository work;
  isolate a timed-out/failed repository without accepting unsafe partial authority.
  **Status:** Beta blocker; change authorized; awaiting Beta v0.3 retest.
- **SS-03-04 — Cancel:** Cancel remained at “waiting for selected work to stop” for over ten
  minutes. Acknowledge immediately, return to the last usable screen within two seconds with
  selections preserved, prevent a new run only while owned cleanup settles, and publish final
  lifecycle evidence. **Status:** Beta blocker; change authorized; awaiting Beta v0.3 retest.
- **SS-03-05 — Window Quit versus service Quit:** Window Quit and the close control end only the
  current run/window and leave the menu-bar service running. Only menu-bar **Quit ShadowSync**
  terminates the service after safe drain. Completed/cancelled read-only work must not leave a
  sticky false task receipt. This does not reopen deferred SS-D001.
  **Status:** Change authorized; awaiting Beta v0.3 retest.
- **SS-03-06 — Exact eligibility diagnostics:** `KleinPerkins/dev` showed only a generic unknown
  cleanliness/index refusal. Preserve the exact bounded failed check or timeout and provide
  reinspection through the normal Reload/Retry path. **Status:** Change authorized; awaiting
  Beta v0.3 retest.
- **SS-03-07 — Multiple operations:** AWA canonical-root selection was valid, but selecting
  Fast-forward plus exact Repair was misreported as checkout ambiguity. Show execution order,
  freshly revalidate before each operation, stop that repository after a failed operation, and
  continue independent repositories safely. **Status:** Beta blocker; change authorized; awaiting
  Beta v0.3 retest.
- **SS-03-08 — Root confirmation:** The four Affirm prompts were correct: they were the only
  selected writable origins without authority records. Preserve this behavior.
  **Status:** Accepted behavior; no corrective flow authorized.

### Beta v0.3 acceptance matrix

- **Previously accepted/preserved:** Menu icon; basic menu; shortcut routing; readable,
  resizable/full-screen window; origin identity and canonical-root UX; Show/Hide grouping;
  Excluded/Protected sections; saved selections; device-only authority refresh.
- **Failed in Beta v0.2:** Multi-repository hydration completion, bounded Cancel, window/service
  Quit semantics, and multiple-operation review.
- **Minor defects in Beta v0.2:** Repeated unavailable reasons, Save window movement, and generic
  eligibility detail.
- **Beta v0.3 build 5:** Merged and installed, but not release-cleared because Continue remained
  disabled after cancellation cleanup reported completion.
- **Beta v0.3 build 6 correction:** Focused regression passed; governed delivery and installed
  retest pending.
- **Not accepted:** Fast-forward execution, refusal/cancel lifecycle, reports/logs, and final Quit
  remain unaccepted until explicit renewed operator UAT.

### Beta v0.3 focused evidence

- `swift build`: PASS after the focused implementation.
- `scripts/verify-beta-v0.2.sh`: PASS — preserved origin-centric chooser and device-drift
  regressions.
- `scripts/verify-beta-v0.3.sh`: PASS — consolidated reasons, in-place Save, one-pass phased
  hydration, bounded lifecycle fallback, cancellation/window-close seams, exact eligibility
  diagnostics, ordered same-repository operations, and `0.3.0 (5)` identity.
- `scripts/verify-beta-v0.3-build6.sh`: PASS — Cancel held the new-run interlock until simulated
  cleanup completion, preserved two selected rows, re-enabled eligible rows, recomputed Continue,
  and admitted the next Continue; `elapsed_ns=49791`, `selected=2`, `continue_count=2`.
- `scripts/beta-v0.3-save-smoke.sh`: PASS — native chooser before/after screenshots were visually
  inspected; status changed to **Defaults saved.** while frame remained exactly
  `3460,591,760,622`.
- `assets/shadowsync-beta-v0.3-premerge-save/01-before-save.png` —
  `1d89f2da46b6e0a37c7bbff5da2583e254e22882d1775783a4ec19913d48d8d5`
- `assets/shadowsync-beta-v0.3-premerge-save/02-after-save.png` —
  `6fec7d7614abe5af3e6179c80332bb0cc56bf4295046dcc48bd2f928b55da723`
- `assets/shadowsync-beta-v0.3-premerge-save/save-frame.txt` —
  `a879fe141f43effcc1dd0f5711f963ae1280035a57a235936fd05edaa480593d`

### Build-5 installed smoke and build-6 correction

- **Build-5 Save:** Passed installed smoke. The chooser reported `Defaults saved.` without moving:
  frame remained `858,283,827,622`.
- **Build-5 Cancel:** The chooser returned with preserved selections and reported
  `Cancelled. Safe cleanup completed; selections were preserved.`, but Continue remained disabled
  for more than two minutes. This blocked the required follow-on hydration.
- **Build-5 window Quit:** Passed. The run window closed, the managed menu service retained the
  same PID, and the service remained running.
- **Root cause:** `updateControls()` calculated selection availability from repository controls
  that were still disabled by the cleanup interlock, then re-enabled the rows without recomputing
  Continue.
- **Build-6 correction:** Re-enable/reconcile repository controls first, then calculate selection
  and canonical-root state. The interlock still disables rows and Continue while cleanup is
  unsettled. **Status:** Fixed — awaiting governed merge, exact-source install, installed retest,
  and operator UAT.

## Beta v0.4 lifecycle-center corrective UAT

The operator explicitly authorized Beta v0.4 after build-6 UAT established that repository-level
Fast-forward readiness was incorrectly coupled to exhaustive branch/worktree/PR cleanup enrichment.
UAT remains open; all prior accepted menu, chooser, authority, cancellation, window-Quit, and
device-drift behavior must remain unchanged.

### Root cause and authorized correction

- **SS-04-01 — P0 Fast-forward readiness:** `makeInventory` serially enriched every local branch
  and worktree under one 20-second clone deadline before constructing the repository card. Large
  repositories therefore timed out, and the lifecycle warning erased otherwise valid canonical
  default-branch relation and Fast-forward evidence. **Authorized:** run bounded canonical/default
  readiness first; cleanup delay or failure must never remove top-level actions.
- **SS-04-02 — Explicit cleanup inspection:** Branch/worktree/PR/AWA cleanup enrichment must not
  run by default or on expansion. Per-repository **Inspect branches & worktrees** and global
  **Inspect for all repositories** controls load/cache optional evidence. Failures remain local to
  the requested cleanup result.
- **SS-04-03 — Lifecycle TLDR:** Repository identity, canonical/default checkout, cleanliness,
  relation, actions, selections, and one actionable blocker remain at top level. Cleanup is last
  and expandable only after inspection; raw identities, refs, OIDs, CAS and command evidence move
  to technical diagnostics.
- **SS-04-04 — Cleanup recommendations:** Use **Protected — cannot remove** and
  **Keep recommended**. Show concrete missing proof, concise file/upstream state, and every
  worktree's AWA management, registration and heartbeat status. A dependency-blocked branch is
  selectable only after every removable claiming worktree is explicitly selected; dependencies
  are not auto-selected.
- **SS-04-05 — Window continuity:** Preserve and clamp frame/screen anchor across chooser,
  lifecycle, review/batch, and completed Close/new-run transitions.
- **SS-04-06 — Review and batch:** Group review by repository and ordered child action, retain
  visible anti-click-through arming, and present selected execution with cumulative progress,
  repository rollups, four plain states, actionable refusal detail, and accessible immutable plan
  record #1.
- **SS-04-07 — Presentation:** Sort chooser rows by normalized owner then repository; remove
  repeated default/canonical cleanup rows and unstable nested whitespace.
- **Release identity:** `0.4.0 (8)`.
- **Status:** Build 7 merged and installed. Its installed smoke confirmed top-level
  Fast-forward/repair actions before cleanup inspection, explicit per-repository/global cleanup
  controls, and grouped review arming. It also exposed one narrow continuity omission:
  recovered completed-batch Close did not preserve its frame for the next run. Build 8 carries
  the recovered frame through the same continuity path already used by live batches.
  Focused `verify-beta-v0.4.sh` passed chooser ordering,
  top-level/cleanup decoupling, explicit cleanup controls, window continuity, grouped review/batch,
  and `0.4.0 (8)` identity. The focused native AppKit lifecycle-layout check passed with 16 cards,
  no ambiguous layout, no overlap, stable leading geometry, and collapsed cleanup disclosures.
  Governed merge, exact-main install, installed smoke, and renewed operator UAT remain required.
  No acceptance is inferred.

### Beta v0.4 acceptance matrix

- **Previously accepted/preserved:** Menu icon/labels/shortcut; native resize/full-screen; chooser
  grouping and origin deduplication; canonical-root Change and persistence; Save/defaults;
  transparent hydration progress; Cancel/Continue recovery; window Quit preserving the service;
  device-only authority refresh.
- **P0 awaiting retest:** Clean Behind canonical/default checkout exposes Fast-forward promptly
  without cleanup inspection.
- **Awaiting retest:** Explicit per-repository/global cleanup controls; lifecycle TLDR and
  diagnostics; AWA status; dependency selection/order; frame continuity; grouped review arming;
  selected-batch rollups and refusal guidance.
- **Still unaccepted:** Actual Fast-forward/repair/removal execution, reports/logs, and final
  menu-bar Quit require renewed operator UAT.

## Beta v0.5 startup and operation-readiness corrective UAT

The operator provided two initial Beta v0.4 UAT rounds and explicitly authorized a Beta v0.5
corrective cut. UAT is not complete. Prior accepted chooser, window, shortcut, canonical-root,
cancel, and lifecycle-center behavior remains in force.

### Authorized feedback and requirements

- **SS-05-01 — Manual startup by default:** ShadowSync must not launch merely because the Mac
  started. The installed launch service remains registered but uses `RunAtLoad=false`; installation
  explicitly launches the newly installed build once. A user who wants automatic startup can add
  the regular ShadowSync app through its **Open ShadowSync at Login** app-menu setting, backed by
  the standard macOS Login Items service so it is visible and removable like another application.
- **SS-05-02 — Normal application presence:** While running, ShadowSync must be a regular macOS
  application in the Dock/app switcher and application menu, and must appear in Force Quit while
  retaining its menu-bar control.
- **SS-05-03 — Menu-bar glyph:** Replace the prior full app mark with a monochrome template image
  of the innermost pull-request glyph used by the application icon.
- **SS-05-04 — Terminal-report Quit:** A durable completed operation report must never force a
  review dialog before application Quit. Preserve the report and show a passive next-launch/menu
  notice when it needs attention. A terminal state without any valid report remains fail-closed.
- **SS-05-05 — Fast-forward readiness at ordinary repository scale:** A repository must not lose
  otherwise safe Fast-forward eligibility because its index exceeds the former 16 KiB process
  output cap. The bounded inventory budget is raised to 32 MiB.
- **SS-05-06 — Repair admission parity:** Runtime admission must use the selected target's fresh
  transaction checks, not reject a selected stale-registration repair because another stale
  registration exists in the repository. The production validator is injected into the focused
  regression so tests exercise the same path.
- **SS-05-07 — Cleanup layout:** Present cleanup as a clear **Optional cleanup inspection** group.
  Its heading and **Inspect branches & worktrees** control are left-aligned with each other.
- **SS-05-08 — Failed operation diagnosis:** The Beta v0.4 all-error run completed before any
  fetch or update mutation. The two independent false blockers were the 16 KiB inventory output
  ceiling and the all-registration runtime gate above; both are corrected in Beta v0.5.

### Candidate status

- **Release identity:** `0.5.0 (10)`.
- **Implementation:** Candidate changes are present on the sanctioned corrective branch.
- **Verification:** Build 9 passed the Beta v0.5 focused suite, DM2 card regression, M5 practical
  suite, complete M6 lifecycle/crash-recovery gate, installer check, model-tier catalog check and
  its 16 tests, and diff hygiene before merge. Its exact-main installed smoke found the fresh Login
  Item omission above. Build 10 treats `.notFound` as an actionable first-registration state,
  retains error reporting if registration actually fails, and unregisters owned temporary app
  bundles before test-root deletion so LaunchServices is not polluted by test copies. The focused
  Beta v0.5 and DM2 card suites and M5 practical gate pass on build 10. Direct cleanup regression
  passes, and the local LaunchServices registry contains only the installed physical app after
  removal of 482 stale test records. The M6 lifecycle run passed all 50 scenarios, 129 recorded
  launch actions, and the complete install/repair/first-install/uninstall hard-crash matrix without
  changing live product state. Broader wrappers retain three base defects outside this correction:
  the documented 100-repository debug timing budget under sustained load, SS-D001's deferred M5
  onboarding-commit Quit assertion, and `verify-m6.sh` matching its own `URLSession` forbidden-token
  test literal as product network code. Governed review/checks, merge, exact-main installation, and
  installed registration-toggle smoke remain pending. No release or UAT acceptance is inferred.
- **Renewed UAT:** Startup/login behavior, Dock/app-menu/Force Quit presence, menu glyph, cleanup
  alignment, selected Fast-forward and exact Repair execution, result report, and ordinary Quit
  all require operator retest after exact-main installation.

## Beta v0.6 admission, ownership, and result corrective UAT

The operator selected a replacement implementation owner after the prior task stalled and
explicitly authorized the Beta v0.6 corrective cut. This authorization permits implementation and
governed delivery only. It does not accept Beta v0.5 or v0.6 UAT, and it does not change any prior
accepted behavior or the deferred `SS-D001` boundary.

### Authorized requirements and status

- **SS-06-01 — Release authority and provenance:** Cut only `0.6.0 (11)` from the exact clean
  baseline recorded above; record the final candidate head, ready PR, controller merge revision,
  exact-main installation, and open-UAT state. **Status:** Implemented and candidate-local
  provenance verified; commit/PR/merge/install receipts are recorded through governed delivery.
  UAT remains open.
- **SS-06-02 — Checked-out unknown-relation admission:** A cached unavailable relation may expose
  Fast-forward only for the exact freshly verified-clean checked-out default target. Execution
  fetches and freshly classifies Equal, Behind, Ahead, or Diverged; unknown ref-only remains
  refused. **Status:** Implemented and focused relation matrix passed; operator retest pending.
- **SS-06-03 — Exact default claimant:** Require one fresh physical default-branch claimant.
  Unrelated stale non-default registrations do not veto Fast-forward; duplicate default claims,
  changed identity, or changed ref still refuse. **Status:** Implemented and focused
  claimant/topology matrix passed; operator retest pending.
- **SS-06-04 — Operation-scoped linked-worktree evidence:** Repair, Fast-forward, and ref-only
  preservation open linked worktrees from fresh marker, registration, gitdir, commondir, HEAD, and
  immutable clone evidence while preserving every lock, exact repair-set, ref, hook, identity,
  digest, postflight, and immediate pre-mutation gate. **Status:** Implemented; focused R01 and
  serial Body 1/Body 4 preservation gates passed, including zero mutation when preserved state
  drifts immediately before prune; operator retest pending.
- **SS-06-05 — New-run ownership:** Start New Run archives or dismisses terminal presentation and
  opens the chooser; only genuinely active or unsettled work blocks. **Status:** Implemented and
  AppKit lifecycle matrix passed; operator retest pending.
- **SS-06-06 — Independent history:** Show Last Report owns a separate read-only historical viewer
  and validated durable snapshot that cannot control or block live work. **Status:** Implemented;
  lifecycle isolation and native historical presentation passed; operator retest pending.
- **SS-06-07 — Same-session delta hydration:** Reconciling A,B to B,C retains unchanged B's
  inspected capability and cleanup evidence, hydrates only C, drops A, and resets action
  selections and confirmations. Actual execution still validates freshly. **Status:** Implemented;
  delta/no-op/changed-binding tests and the C-only onboarding continuation passed; operator retest
  pending.
- **SS-06-08 — Cleanup bulk-selection gate:** Select All Recommended Cleanup remains disabled until
  at least one cleanup inspection succeeds, then selects only eligible recommendations from
  successfully inspected repositories. Manage remains disabled while inspection is in flight.
  **Status:** Implemented; zero/success/failure/mixed inspection matrix passed; operator retest
  pending.
- **SS-06-09 — Stable repository/action results:** Present left-aligned, width-constrained logical
  repository groups with persistent planned-action rows and stable row identity from queued through
  terminal. Public bounded outcome text is inline; command events update only Live Log.
  **Status:** Implemented; row-identity/command-isolation checks and native visual inspection
  passed; operator retest pending.
- **SS-06-10 — Historical metadata:** Derive start, end, duration, repository list/count, attempted
  action count, and terminal outcome counts from durable run evidence for both live completion and
  historical replay. **Status:** Implemented; deterministic live/historical checks and native
  presentation passed; operator retest pending.
- **SS-06-11 — Bounded diagnostics and compatibility:** Carry additive optional redacted and capped
  technical detail through Body 3 outcome, result, log, reconstruction, and presentation while
  preserving decoding of older valid v2 logs. **Status:** Implemented; redaction/cap/refusal tests,
  source-doctor timing/count parity, and pinned old-v2 decoding passed; operator retest pending.
- **SS-06-12 — Verification, governed delivery, and UAT:** Add the focused v0.6 selector/wrapper,
  prove the closed relation/topology/session/UI/compatibility matrix, open a ready exact-head PR,
  leave review/check/merge to controller automation, install only exact merged main, and hand off
  renewed UAT without claiming acceptance. **Status:** Focused/practical/native/source gates
  complete; exact-head proof, ready PR, controller checks/merge, exact-main install/smoke, and
  renewed operator UAT are recorded only through governed delivery.

### Candidate-local verification receipt — 2026-10-05

- `scripts/verify-beta-v0.6.sh` passed the complete focused selector, including checked-out
  relation/topology cases, R01 preservation, same-session reconciliation, cleanup gating, stable
  result ownership, historical metadata, diagnostics, and old-v2 compatibility.
- Serial `scripts/v2-body1-acceptance.sh`, `scripts/v2-body4-acceptance.sh`, and
  `scripts/verify-m5.sh --practical-only` passed. The Body 4 receipt includes production signing,
  lifecycle preservation, source-doctor acceptance of canonical optional technical detail, and
  refusal of unredacted token/path detail, contradictory timing, and forged repository totals.
- A bounded release review found and closed two additional edge cases: Repair now revalidates
  preserved linked-worktree state immediately before prune, and onboarding after A,B to B,C keeps
  B while refreshing only C. Re-review found no remaining actionable P0/P1/P2 issue in those paths
  or diagnostic compatibility.
- Native AppKit captures were inspected at queued, running, terminal, and historical replay states.
  Repository groups remained left aligned and bounded, action rows stayed present, command evidence
  stayed out of result rows, terminal metadata/counts and redacted detail were readable, and the
  historical title was `ShadowSync · Last report (read-only)`. The visual host and capture scratch
  were removed afterward.
- The pinned pre-v0.6 fixture
  `Tests/ShadowSyncSelfTests/Fixtures/pre-v06-v2-latest.log` has SHA-256
  `127c4530f3d071f66b283363eaf81f9fdef9c51a8dff6389128d9b04e0815f0a` and decodes with the
  additive field absent.
- `install.sh --check`, the portable source contract, script syntax, and `git diff --check` passed.
  The full Body 2 and Body 3 aggregate lanes stop on inherited closed-oracle assertions
  (`DM2-T07` and `Recommended clean cleanup planned an inapplicable recovery artifact`);
  both failures reproduce from isolated archive bytes at exact baseline
  `1674a878e7b0cb38049796e3df232b6f753a0996`. The repository gate likewise reaches inherited
  `DM3-T07 invalidDocument`, reproduced from that same baseline after `DM3-T01–06` pass.
- Doc-warden reports this plan and ADR 0005 conformant. Its overall drift is limited to the three
  pre-existing unrelated plans `agent-route-feedback-loop-v1.md`,
  `dev-main-sync-global-capability-v5.md`, and
  `subagent-orchestration-sibling-assets-v1.md`.
- These receipts prove candidate behavior only. They do not install branch bytes, declare a
  release, or accept any UAT row.

### Candidate acceptance boundary

- **Previously accepted/preserved:** Menu icon; basic menu and shortcut; readable native window;
  origin-centric chooser and canonical-root authority; device-only authority refresh; Save
  stability; bounded Cancel and window Quit; explicit optional cleanup inspection; and manual
  startup/application-presence requirements.
- **Corrective retest required:** Checked-out unknown-relation Fast-forward, exact default claimant,
  stale-registration Repair/preservation, terminal-to-new-run routing, independent history,
  same-session delta hydration, cleanup bulk gating, stable grouped results, historical metadata,
  diagnostics, and old-log compatibility.
- **Still unaccepted:** Actual Fast-forward, Repair, removal/retention execution, refusal/cancel
  lifecycle, reports/logs, installed Login Item behavior, and final menu-bar Quit remain open until
  explicit renewed operator UAT.

## Deferred engineering

### SS-D001 — Quit during onboarding-authority commit

- **User-visible impact:** If Quit is requested while canonical-root onboarding is committing,
  ShadowSync can remain open after that commit settles instead of completing the deferred Quit.
- **Observed beta:** The focused M5 confirmation-close harness deterministically reports
  `onboardingCommitQuitServiced=false`; the stale drain receipt remains fail-closed.
- **Reason deferred:** The narrow timing does not block launch, selection, safe sync, or ordinary
  Quit, and it exposes no credential or destructive/data-loss path. Preserving the app is safer
  than terminating without complete drain evidence.
- **Priority suggestion:** P1 candidate for an operator-approved MVP hardening pass.
- **Reconsideration trigger:** Promote immediately if hands-on review reproduces it in ordinary
  Quit, strands an active operation, prevents safe relaunch/repair, or shows state loss.
- **Status:** Deferred for Beta v0.1; not accepted for MVP work without explicit operator approval.

## Operator feedback and acceptance

Update each entry with the operator's own observed result and keep feedback open until clarified.
`Pending` and successful automated evidence are not acceptance.

### Requirement/workflow status

- **UAT-01 Menu-bar icon appearance:** Accepted for failed build `0.1.0 (1)`.
- **UAT-02 Basic menu:** Fixed — awaiting operator retest.
- **UAT-03 Shortcut invocation:** Fixed — awaiting operator retest.
- **UAT-04 Start New Run window/core flow:** Failed / Beta blocker; corrective implementation
  passed focused and native visual smoke — awaiting operator retest.
- **UAT-05 Native visual smoke gate:** Pre-merge native geometry and controlled full core happy
  path passed; build-5 installed smoke found the post-cancel Continue blocker. Build-6 corrective
  retest remains open.
- **SS-F001 Launch and reopen:** Fixed — awaiting merged installed-app smoke and operator retest.
- **SS-F002 Choose repositories and save defaults:** Not tested in operator UAT.
- **SS-F003 Confirm canonical roots:** Not tested in operator UAT.
- **SS-F004 Fast-forward and verified no-op:** Not tested in operator UAT.
- **SS-F005 Safe refusal and cancellation:** Build-5 installed smoke failed post-cleanup
  re-admission; build-6 correction passed focused regression and awaits installed/operator retest.
- **SS-F006 Report, log, and Quit:** Not tested in operator UAT.
- **SS-D001 onboarding-commit Quit defect:** Operator-deferred for Beta v0.1 unless blocker
  evidence triggers reconsideration; this is not acceptance of SS-F006.

### SS-F001 — Launch and reopen

- **Workflow:** Install or open ShadowSync, then open it again.
- **Expected / observed:** One managed host opens or foregrounds the current chooser/window;
  failed build `0.1.0 (1)` opened an unreadable narrow chooser. The build-2 candidate passed
  focused geometry assertions and visually inspected native initial/resize/full-screen/restore
  smoke; merged installed-app verification remains open.
- **Operator feedback:** Failed candidate clearly reported in UAT-03/UAT-04.
- **Requirement / design / UX impact:** Authorized readable native geometry and common menu/shortcut
  route implemented.
- **Disposition:** Fixed — awaiting merged installed-app smoke and operator retest.
- **Requirement status:** Fixed — awaiting retest.
- **Acceptance:** Pending explicit operator decision.

### SS-F002 — Choose repositories and save defaults

- **Workflow:** Select repositories, save defaults, reopen, edit, and recover malformed defaults.
- **Expected / observed:** Only governed eligible repositories can be selected; persistence is
  conflict-safe and recovery requires confirmation. The practical M5 chooser check passed disabled
  reasons/counts, selection/review exclusion, compact locations, and a process/network-free first
  screen. Operator UX review is pending.
- **Operator feedback:** Pending.
- **Requirement / design / UX impact:** Pending.
- **Disposition:** Ready for hands-on review.
- **Requirement status:** Not tested.
- **Acceptance:** Pending explicit operator decision.

### SS-F003 — Confirm canonical roots

- **Workflow:** Continue with an unresolved repository, confirm its canonical clone, and return to
  repository cards.
- **Expected / observed:** Confirmation records authority only; it does not fetch or update. A
  fresh selected-only inventory gates cards. Focused DM3 selection/lifecycle checks passed;
  operator review is pending.
- **Operator feedback:** Pending.
- **Requirement / design / UX impact:** Pending.
- **Disposition:** Ready for hands-on review.
- **Requirement status:** Not tested.
- **Acceptance:** Pending explicit operator decision.

### SS-F004 — Fast-forward and verified no-op

- **Workflow:** Update one approved clean Behind repository, then run an Equal repository.
- **Expected / observed:** Behind advances only by captured-OID `--ff-only`; Equal is a verified
  no-op. The six focused Body 1 fixture families passed, including remote-default resolution,
  checked-out-target updates, hooks, cards, and lifecycle; live repository review is pending.
- **Operator feedback:** Pending.
- **Requirement / design / UX impact:** Pending.
- **Disposition:** Ready for hands-on review using an approved disposable or low-risk repository.
- **Requirement status:** Not tested.
- **Acceptance:** Pending explicit operator decision.

### SS-F005 — Safe refusal and cancellation

- **Workflow:** Observe a blocked/dirty/ahead/diverged repository and cancel selection or a run.
- **Expected / observed:** Blocked rows never enter work; drift and unsafe states refuse without
  mutation; cancellation drains owned work. Focused Body 1 and practical M5 refusal/selection
  checks passed. Operator clarity review is pending.
- **Operator feedback:** Pending.
- **Requirement / design / UX impact:** Pending.
- **Disposition:** Ready for hands-on review.
- **Requirement status:** Not tested.
- **Acceptance:** Pending explicit operator decision.

### SS-F006 — Report, log, and Quit

- **Workflow:** Finish or cancel a run, reopen its report/log, close it, and Quit.
- **Expected / observed:** Results remain ordered and durable; ordinary Quit drains before exit.
  The narrow onboarding-commit Quit regression is tracked as SS-D001.
- **Operator feedback:** Pending.
- **Requirement / design / UX impact:** Pending.
- **Disposition:** Ready for hands-on review with SS-D001 disclosed.
- **Requirement status:** Not tested.
- **Acceptance:** Pending explicit operator decision.

## Beta v0.7 performance, Repair-copy, and hierarchy corrective UAT

The operator completed the first successful selected batch: 20 of 20 actions succeeded over five
repositories. The durable report contained 816 records, including 745 command records, reached a
50-events/second peak, and occupied 786 KB. This validates the existing operation and safety flow;
it does not close UAT.

During that run macOS reported the application unresponsive before it recovered without force quit.
The preserved CPU diagnostic recorded 90 CPU seconds over 146 seconds (62% average), with 24 of 26
samples in `Body3RunWindowController.update → Body3RunLogReader.render → NSRegularExpression`.
The v0.6 path scheduled one main-actor task per event, re-rendered/redacted the complete record
prefix, and replaced the `NSTextView` even while Live Log was collapsed. Memory remained near
100 MB. The operator approved a bounded rendering correction, not scheduler or operation changes.

Read-only lifecycle inspection confirmed 11 stale registrations across 7 of 19 catalog
authorities. `dev`, `intent-router`, and `skills` contained detached stale registrations that
cannot satisfy independent removal proof alongside branch-backed registrations. Git's exact prune
set remains correctly all-or-nothing. The operator approved neutral unavailable-action copy and
technical-detail relocation; detached removal remains refused.

### Authorized requirements and status

- **SS-07-01 — Release authority:** Cut only `0.7.0 (12)` from the exact baseline, branch, and
  accepted plan recorded above. Preserve ADR 0005 and the v0.6 plan byte-identically; keep UAT open.
  **Status:** Implemented; branch, immutable plan, release identity, and open-UAT boundary verified.
- **SS-07-02 — Linear, lazy Live Log projection:** Redact/render each new record once, retain the
  131,072-character bounded suffix, skip visible-log replacement while collapsed, and perform one
  bounded catch-up on expansion. **Status:** Implemented; 1,632-record, Unicode/UTF-16, redaction,
  collapsed/expanded, and exact-rendering regressions pass.
- **SS-07-03 — Coalesced UI delivery and evidence:** Coalesce ordered event/UI-log work; preserve
  append-only logging, immutable plans, cancellation, confirmations, and two-worker execution.
  Capture non-sensitive update duration, backlog, coalesced render count, rendered characters, and
  heartbeat latency; deterministic invariants replace a timing SLA. **Status:** Implemented;
  production delivery-path, backlog, render-count, character-count, update-duration, and heartbeat
  evidence regressions pass without changing worker count or execution semantics.
- **SS-07-04 — Truthful unavailable Repair:** Preserve the exact safety gate. Render an unattempted
  unavailable optional Repair neutrally with generalized detached/unproven counts and “Nothing will
  be changed.” Put registration identifiers/proof reasons only in Technical diagnostics. Reserve
  orange/error presentation for attempted refusal/failure. **Status:** Implemented; mixed,
  fully-repairable, no-stale, count/pluralization, diagnostics, and unchanged-gate regressions pass.
- **SS-07-05 — Stable visual hierarchy:** Preserve stable cards/rows. Use a 13-point semibold
  repository parent with trailing `N of M steps`; 24–28-point child indentation; a 1-point vertical
  connector and horizontal elbows; 12-point regular child titles; 11-point details; neutral action
  titles; and semantic icon/detail colors across queued, running, terminal, and historical states.
  No `NSOutlineView` rewrite. **Status:** Implemented; geometry, identity, accessibility, queued,
  running, terminal, historical, and native visual evidence pass.
- **SS-07-06 — Verification and governed delivery:** Add a focused v0.7 selector/wrapper; prove
  deterministic high-volume, core, AppKit, native visual, installer/source, repository, doc, and
  diff gates at one exact clean head; inspect captures; open one ready PR; and leave review/merge to
  controller automation. Do not install before merge. **Status:** Delivered through ready PR #219,
  controller exact-head approval, exact-tree merge, exact-main installation, and installed native
  smoke. UAT remains open.

### Candidate-local verification receipts

- `scripts/verify-beta-v0.7.sh`: PASS — Body 2 R01 safety/copy matrix; 1,632-record linear
  projection; reusable redaction expressions; Unicode/UTF-16 incremental mutation; production
  event delivery; collapsed catch-up; stable hierarchy; and source/release assertions.
- `scripts/verify-m5.sh --practical-only`: PASS — production/testing bundle construction,
  DM3-T04/T11/T12/T14, practical AppKit selection behavior, and first-screen process/network
  metrics.
- `install.sh --check`: PASS. `v3-preflight-acceptance.sh --portable-source-contract`: PASS.
- Native queued, running, terminal, and historical captures were visually inspected. Repository
  parents, `N of M steps`, 26-point-indented children, connector trunks/elbows, neutral action
  titles, semantic status details, historical metadata, and left alignment were readable without
  clipping. Capture SHA-256 values were `c6753eb22945eda57e0f0d4bf5899962002d2ab9e49372a922d9aaf26714933f`,
  `d37836668f235b7c357e110440725edfcd8d1ba0ff7ba12ab8a5e3720b37ecca`,
  `5620b04aa90ed8d7473a61f033d9111e35ced4ea7ce5f00ef5234938bcdacbd3`, and
  `c0d46d499e3f1621fbb923b8250b0c15401f5b5638b4b759c8415934e17fbb2e`.
- `.github/scripts/verify-skills.sh`: repository-wide checks reached the inherited macOS
  `DM3-T07` authority-stage fixture, then reported `invalidDocument`. The same isolated selector
  fails identically from an untouched `origin/main` archive at
  `c95c4009226b8385d8bf222a0da31f14de1817f2`; this is pre-existing baseline drift, not a v0.7
  regression. The Linux/portable source contract passes. This bounded correction does not alter
  selection-document validation or selected-hydration binding code.
- `doc-warden check`: changed v0.7 plan/index and ShadowSync ADR/plan authorities conform; overall
  repository status remains DRIFTED only for the three pre-existing unrelated plan records.
  `git diff --check` passes. Accepted ADR 0005 and v0.6 plan bytes remain unchanged.

### Exact merged-main release receipt

- Ready PR #219 reviewed exact head `441bc6c890245c187d95abd6b6f0eceb9d66283c`; all controller
  checks passed and controller approval named that exact head. The PR merged as
  `c2f04756f6f5c71a05eadc9bee76606b254fc0e3`. Reviewed and merged source have the identical
  tree `2fc87729139a10f1b47b0f903d26accf15fa284b`.
- The governed exact-main source, release-build, and focused v0.7 gates passed. The focused receipt
  reconfirmed the deterministic high-volume linear-log path, collapsed-log laziness, coalesced
  delivery, reusable redaction expressions, neutral unavailable Repair, stable hierarchy, and
  bounded UI-work instrumentation.
- The ordinary installer path safely refused the managed prior install because its source identity
  differed. The documented governed repair path then installed `0.7.0 (12)` from the exact merged
  source. Source revision is `c2f04756f6f5c71a05eadc9bee76606b254fc0e3`; source-input SHA-256
  is `061eddb2a192bd15cc7a739807c9c64a97f54a86e8746c831eb83e360db6a8ee`; metadata-contract
  SHA-256 is `08d13f1f8425e952a2aa6d8662eebc846066d135fec806f82b14ba44b9175b5f`; and installed
  bundle SHA-256 is `dd0f6bab0c1a5303037cc35b0ebc1b968ca284ce0f76d16bb6887242211c74aa`.
- Installed doctor, designated-requirement signature, bundle identity
  `com.kleinperkins.dev-main-sync`, LaunchAgent host, and process readiness passed. Native smoke
  proved the chooser, independent read-only Last Report, Start New Run routing back to the chooser,
  ordinary Quit/drain, and healthy relaunch. The installed historical report visibly preserved the
  left-aligned repository/action hierarchy, stable cards, step totals, indentation, and connector
  lines. No repository operation or saved selection was changed.
- The installed application remains available at the chooser for renewed operator UAT. Engineering
  delivery and installation do not accept or close UAT.

### Preserved non-goals

- No granular prune, detached-commit preservation/removal, preservation store, worker-count change,
  arbitrary performance SLA, outline/tree rewrite, external telemetry, dependency, or unrelated
  cleanup.
- No live repository mutation for verification and no replacement of installed `0.6.0 (11)` before
  an exact merged-main release task.
- Engineering completion and a successful PR do not accept or close operator UAT.

## Beta v0.8 bounded-output and presentation corrective UAT

The v0.7 operator run `24c274d8-8c8d-49e3-94d0-6f5193e47dc3` completed 18 terminal actions across
nine repositories: 13 succeeded, two skipped, and three failed. The preserved 941,529-byte durable
log contains 502 records, including 446 command records, and has SHA-256
`e2363b94d730d71830d271e66ab4f311693699cf9affecb2f7b02aab9b0ea415`.

`pr-automation-controller` was the only proven freshness refusal: its repository configuration
identity changed after planning. `dev` and `skills` were false failures. Their successful
`git ls-files -v -z` commands produced 26,854 and 55,578 bytes, respectively, above the execution
runner's 16,384-byte capture limit. Truncation was then misreported as `git ls-files failed (0)`,
normal filenames entered technical detail, and every admitted command inherited the aggregate
operation failure code. Six of 19 catalog authorities exceed the old execution bound. Inventory
already uses a bounded 32 MiB capacity; exact Repair/preservation also requires complete index
evidence.

`dev`'s clean checked-out `main` and cached `origin/main` matched, while the advertised remote OID
was newer and not yet present locally. Internal `.unavailable` is conservative and remains correct
until guarded fetch; the presentation did not explain that known state. Six of 19 catalog
authorities had stale cached tracking versus the advertised remote during the read-only scan; only
`dev` was in the saved selection.

The v0.7 performance correction held. The real run recorded 501 UI records, maximum backlog six,
492 event batches, zero visible-log renders while collapsed, 187,019 projected characters,
maximum main-actor update 3.356 ms, and maximum heartbeat latency 12.311 ms. No hang/spin report
was produced and the installed process returned to approximately 37 MB resident memory. Sustained
expanded Live Log remains a candidate verification signal, not a new SLA.

### Authorized requirements and status

- **SS-08-01 — Release authority:** Cut only `0.8.0 (13)` from exact baseline
  `7c5e4c8efdb26b245cdc27a87765056df67dc753` on
  `fix/shadowsync-beta-v0.8-build13`; preserve ADR 0005 and accepted v0.6/v0.7 plan bytes; keep UAT
  open. **Status:** Authorized; accepted v0.8 plan v1 records the closed scope.
- **SS-08-02 — Complete bounded execution evidence:** Use the existing 32 MiB inventory capacity
  only for execution and exact Repair/preservation paths requiring complete output. Keep explicit
  truncation refusal above the bound. **Status:** Implemented in the v0.8 candidate; focused
  large-index Fast-forward and exact Repair/preservation fixtures passed.
- **SS-08-03 — Truthful diagnostics and command records:** Distinguish successful truncation from
  nonzero exit, omit ordinary index stdout/filenames from errors, and label command audit rows as
  admitted rather than inheriting terminal operation status. Preserve genuine drift refusal copy.
  **Status:** Implemented in the v0.8 candidate; status-zero overflow and filename-omission
  regressions passed.
- **SS-08-04 — Conservative relation presentation:** Keep internal `.unavailable` and execution
  gates unchanged. For stale tracking versus advertised remote, render exactly
  `Default relation: Remote changed since last fetch · exact comparison pending`, followed by
  `Ready after fresh safety revalidation.` **Status:** Implemented in the v0.8 candidate; missing,
  stale, and exact cached-relation regressions passed.
- **SS-08-05 — Dynamic cleanup-panel appearance:** Resolve a named dynamic fill by blending
  `.windowBackgroundColor` 8% toward `.labelColor` under the effective appearance; preserve
  semantic text, separator, and standard-control colors. **Status:** Authorized; implementation
  complete; Aqua and Dark Aqua native captures were inspected and the deterministic contrast
  checks passed.
- **SS-08-06 — Local completed-report metadata:** Remove repository names; show local 12-hour
  start/end timestamps with AM/PM and timezone abbreviation; show canonical rounded
  days/hours/minutes/seconds; retain repository, attempted-action, and nonzero terminal outcome
  counts. **Status:** Implemented in the v0.8 candidate; deterministic PDT/PST, duration-boundary,
  historical-report, and native completed-report checks passed.
- **SS-08-07 — Verification and governed delivery:** Prove large-index Fast-forward and exact
  Repair, over-limit/hidden-index/drift refusal, relation states, deterministic timezone/DST and
  duration boundaries, Aqua/Dark Aqua visuals, collapsed/expanded high-volume behavior, release
  identity, full governed gates, and one ready PR. Controller automation alone reviews and merges;
  no candidate install. **Status:** Delivered through the reviewed implementation and narrow
  durable-log correction, exact-final-main installation, and installed smoke recorded below.
  Operator UAT remains open.

### Exact final merged-main release receipt

- Ready PR #221 reviewed implementation head
  `53a01d7b823c2f6be8d33a1beadd66d2b094b108` and merged as
  `fb008b72df833ba384b351b97eca4ece7c7839ca`; both have tree
  `f72d2085534cbb5d828fbaa27ba0b61f5fb13d88`. Ready corrective PR #222 reviewed head
  `2a19dbcfde19f26213161ac13db284aaf30fc6bb` and merged as final source
  `840cecad37bc03c5b547f3378e78a5416aa181e3`; both have tree
  `3f1bd1a9c1f8735427460f9f5ae96a172e7d79a9`. The final source descends from PR #221 and differs
  only in the v2 durable-log validator plus its focused lifecycle regression.
- Exact-final-main focused v0.8, DM2-T13 lifecycle compatibility, and signed release-build gates
  passed. A read-only preflight admitted all 502 preserved v0.7 records, including the three
  writer-owned `technicalDetail` records, rejected an injected unknown sibling key in memory, and
  left the 941,529-byte durable log at SHA-256
  `e2363b94d730d71830d271e66ab4f311693699cf9affecb2f7b02aab9b0ea415`.
- The ordinary installer safely refused the stopped managed v0.7 state before mutation. The
  documented governed repair path then installed `0.8.0 (13)` from final source
  `840cecad37bc03c5b547f3378e78a5416aa181e3`. Source-input SHA-256 is
  `7cf08ccb231f2699c3c30051efc67568d62e7d1b444931feb5ffed500135c632`,
  metadata-contract SHA-256 is
  `08d13f1f8425e952a2aa6d8662eebc846066d135fec806f82b14ba44b9175b5f`, and installed bundle
  SHA-256 is `c454f7e8484f2e929d2f8bd440c2486120db421d699d6e96b040c8160790ec06`.
- Installed doctor, designated-requirement signature, bundle identity
  `com.kleinperkins.dev-main-sync`, LaunchAgent readiness, chooser, independent read-only Last
  Report, Start New Run routing, ordinary Quit/drain, and healthy relaunch passed. The report
  visibly retained local 12-hour PDT timestamps, canonical duration, count-only summary, and the
  accepted repository/action hierarchy. No repository operation, registration, or saved selection
  was changed; the durable-log hash remained unchanged. The installed application remains running
  at the chooser for renewed operator UAT.

### Preserved boundaries

- Every freshness, identity, exact Repair-set, preservation, lock, ref, hook, digest, postflight,
  and immediate pre-mutation gate remains unchanged.
- The accepted repository/action connector hierarchy remains unchanged.
- No streaming subprocess redesign, direct-index-only workaround, worker-count change, cleanup or
  pruning semantics, granular prune, new dependency, telemetry, or unrelated cleanup is in scope.
- Installed `0.7.0 (12)`, live repositories, saved selection, stale registrations, and preserved
  UAT evidence remain untouched. Engineering delivery does not accept or close UAT.

## Beta v0.9 bounded inspection performance, progress, and hierarchy corrective UAT

The installed v0.8 RLCC optional inspection exposed one structural performance boundary and one
coherent presentation gap. `KleinPerkins/awa` has 21 total worktrees and 75 branches, displayed as
20 cleanup worktrees and 74 cleanup branches. Read-only profiling measured 4.506 seconds for
worktree state, 230 serial local Git children over 11.870 seconds, and representative per-branch
GitHub lookups averaging 625 milliseconds, projecting about 58 seconds against the fixed 20-second
enrichment deadline. Five of the 11 selected repositories exceed the practical current threshold.

The RLCC also retained only start/end inspection state, stretched summary controls under width
alignment, used literal whitespace for candidate indentation, and placed long identities beside
badges without a narrow-width reflow contract. The operator approved one bounded read-only
inspection correction, not cleanup/removal or mutation changes.

### Authorized requirements and status

- **SS-09-01 — Release authority:** Cut only `0.9.0 (14)` from exact clean baseline
  `3376dd35af3457ae97dd7d6ba6cab73cfbbb8201` on
  `fix/shadowsync-beta-v0.9-build14`; preserve ADR 0005 and accepted v0.6–v0.8 plan bytes; keep UAT
  open. **Status:** Delivered through exact-tree PR #224 merge, exact-main installation, and the
  installed smoke receipt below; UAT remains open.
- **SS-09-02 — Bulk bounded local evidence:** Replace per-branch Git subprocess fan-out with
  bounded bulk local identity/upstream/relation discovery. Any unproven fact remains unavailable.
  **Status:** Implemented; exact-main high-volume relation fixtures passed.
- **SS-09-03 — Dedicated bounded PR admission:** Permit at most four concurrent read-only PR
  children for the current repository only, retaining a 15-second per-query bound and strictly
  sequential top-to-bottom repository processing. Global mutation and unrelated subprocess
  admission remain unchanged. **Status:** Implemented; maximum active PR children remained four
  and repository processing remained serial in exact-main fixtures.
- **SS-09-04 — Adaptive fail-closed completion:** Derive a bounded stage/repository budget from
  admitted work with a hard ceiling. Deadline/cancellation drains owned children, retains fully
  proven candidates, and marks incomplete candidates unavailable/retain and ineligible for bulk
  recommendation. **Status:** Implemented; delayed/error/timeout/cancel and partial-evidence
  regressions passed without admitting incomplete cleanup.
- **SS-09-05 — Retained inspection progress:** Present coalesced topology, worktree, branch, PR,
  and assembly stages. Single inspection retains one bar; inspect-all retains one overall bar and
  stable ordered repository rows through terminal completion. **Status:** Implemented; retained
  single/all progress, ordered terminal rows, heartbeat, cancellation, and drain fixtures passed.
- **SS-09-06 — Coherent RLCC alignment:** Lead-align ordinary headers, copy, controls, names, and
  inline text; reserve trailing alignment for compact status/count badges; replace whitespace
  indentation with constraints; wrap long identities and reflow status below at narrow widths.
  **Status:** Implemented; minimum/standard/wide Aqua and Dark Aqua native captures passed.
- **SS-09-07 — Contained candidate hierarchy:** Keep repository identity/default/actions/optional
  inspection order and render each branch/worktree as a contained subcard with provenance,
  actions/errors, recommendation/rationale, notes, and disclosed diagnostics. Preserve semantic
  colors, keyboard/VoiceOver behavior, muted panel treatment, and selected-batch hierarchy.
  **Status:** Implemented; native hierarchy, wrapping, accessibility, and keyboard-order checks
  passed.
- **SS-09-08 — Bounded instrumentation:** Record aggregate stage counts/durations, active/max
  child count, deadline/partial counts, and progress heartbeat without paths or branch names.
  Exact-key in-session memoization is permitted; durable cache and unbounded events are not.
  **Status:** Implemented; exact-main aggregate stage receipts and bounded memoization tests
  passed.
- **SS-09-09 — Verification and governed delivery:** Prove deterministic 21-worktree/75-branch and
  20-worktree/84-branch fixtures, delayed/error/timeout/cancel adapters, maximum-four child and
  one-repository limits, partial-result safety, zero mutation, progress retention, native
  Aqua/Dark Aqua layout/accessibility, source/release/governance gates, and one ready PR. Controller
  automation alone reviews and merges; no candidate install. **Status:** Delivered through
  controller-approved PR #224, exact-main gates, governed repair installation, and installed smoke.

### Exact merged-main release receipt

- Ready [PR #224](https://github.com/KleinPerkins/skills/pull/224) reviewed implementation head
  `21ceb4f980af9cc842c8f1044cdb43f400ea2841` and merged as exact canonical source
  `c3b564f2834d06c1d752e57c68c4a32ecd883f11`. Reviewed and merged source have the identical tree
  `a1b4db3cfa5fcdc6470d99c8e3d43a4c13346c46`.
- The exact-main focused v0.9 gate passed the 21-worktree/75-branch AWA-shaped fixture in 9.051
  seconds and the 20-worktree/84-branch skills-shaped fixture in 8.965 seconds. Both retained
  maximum PR concurrency four. Bulk relation, partial-result refusal, cancellation/drain,
  inherited bounded-index, progress/hierarchy, and Aqua/Dark Aqua native gates passed. These are
  release receipts, not permanent performance SLAs.
- The ordinary installer safely refused the stopped managed v0.8 state before mutation. The
  documented governed repair path then installed `0.9.0 (14)` from exact merged source
  `c3b564f2834d06c1d752e57c68c4a32ecd883f11`. Source-input SHA-256 is
  `16465f28bb809c79e33be02838349d2b8dac86c4133d01394038e18a51d027a8`,
  metadata-contract SHA-256 is
  `08d13f1f8425e952a2aa6d8662eebc846066d135fec806f82b14ba44b9175b5f`, and installed bundle
  SHA-256 is `f3c0d6bcd3e26f5be5b7f8eed23d421e11b0a18ec59ef507269b20eebb08c33f`.
- Installed doctor, designated-requirement signature, bundle identity
  `com.kleinperkins.dev-main-sync`, LaunchAgent readiness, managed host, chooser, independent
  read-only Last Report, Start New Run routing, ordinary Quit/drain, and healthy relaunch passed.
  Inspection behavior was exercised only through exact-main isolated fixtures; no live inspection,
  saved selection, cleanup, or repository mutation was initiated.
- The preserved 941,529-byte v0.7 UAT log remains SHA-256
  `e2363b94d730d71830d271e66ab4f311693699cf9affecb2f7b02aab9b0ea415`. Repository authorities
  remain `e67c85cff1d40df53143f11bd5192c6e93d195d2695b326a9dafbc45a462ff2f` and saved selection
  remains `183809f761ce81814a1a32adc197f50de90761791bcc24e33c79ad672594fa75`.
  The installed application remains running at the chooser for operator UAT; installation does
  not infer acceptance.

### Preserved boundaries

- Cleanup/removal permissions, exact candidate identity, AWA/recovery/secret/upstream proof,
  mutation gates, selected-batch workers/hierarchy, saved selection, and live repositories do not
  change.
- No granular prune, repository-wide GitHub batching, global concurrency change, durable
  inspection cache, performance SLA, `NSOutlineView`, new dependency, or unrelated cleanup.
- The prior v0.8 live RLCC session could not survive its stopped process, but its durable UAT log,
  authorities, and saved selection remain byte-identical through v0.9 installation. Engineering
  delivery does not accept or close UAT.
