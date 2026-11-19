# Source review scenarios

These synthetic cases are the rubric for independent review of the entry
instructions. They are not executions of a native client or permission canary.

| Case | Supplied evidence | Expected behavior |
|---|---|---|
| Correct placement | Native root, cwd, remote, common/per-worktree directories and owner writer match | Report already-correct; keep permission status separate and continue only authorized work. |
| Wrong project | Known owner differs from this chat's project; native contract cannot change the calling chat's project | Report unsupported with the exact project to open; do not claim a shell move or create a chat without explicit authority. |
| Missing transition | Owner known; no suitable attachment; attach/create surface absent | Report needs-workspace/unsupported and an exact operator action; no fabricated move. |
| Access denied | Correct root, explicit runtime denial | Report needs-access and use the runtime permission route; no relocation to bypass it. |
| Access unknown | Correct root; no authoritative permission information | Keep access unknown; use normal permission handling for the first necessary authorized mutation; no disposable test writes. |
| Stale attachment | Earlier attachment names the target; current native root differs | Reobserve current state, verify identity and report mismatch; do not treat the earlier attachment as current. |
| Partial attachment | Transition returns a handle or transport error without current root evidence | Treat outcome as unverified and inspect native state; no blind retry or success claim. |
| Foreign writer | Correct repository/worktree with a live foreign writer | Stop edits there; follow the owner-approved separate-worktree route; do not steal a lease. |
| Known owner, no index | Explicit repository supplied; index/tool unavailable | Verify that repository directly and continue authorized entry; missing search must not block it. |
| Unknown owner, no index | No owner identity and no eligible index | Ask one bounded ownership clarification; no broad discovery or guessed primary root. |
| Conflicting candidates | Same name at different logical repositories/clones | Preserve distinctions and clarify; ranking supplies no permission or owner decision. |
| Wrong installed layout | Copied skill or missing/mismatched same-root tool | Report search dependency unavailable; no PATH fallback, recursive search or automatic installation. |
