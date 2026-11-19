# Current Codex collaboration profile: build 24141

Observed 2026-11-05 on Codex desktop 26.1027.61615 (24141), using
`collaboration.spawn_agent` and `fork_turns: "none"`. This is separate from the
[accepted legacy screen](../README.md), whose bytes are unchanged.

[Native results](native-screen.json) record both frozen fixtures in each difficulty
band on the preferred and stronger comparison routes: **16/16 pass**, eight per
route. Exact per-run native offer observations, ready decisions, completed
observations, and synthetic answers are included. Fixture definitions remain at
[fixtures.json](../fixtures.json).

The tested Skills revision is `1d6bb65ff127a717ccf047cc9f31405f7bbc2bd2`; its
three-file payload is
`4cfb6f107e5a26dbea73c83bf35d4c918dbc73e0ba26498d2605de9ac71a5ba3`.
Subsequent main refresh and evidence additions leave those three payload files
byte-identical. Consumers must bind the eventual merged source revision separately.

## Review and verification

Two separate fresh-context ordinary Codex workers reviewed code and security. Both
reported no actionable findings. These were context-independent, same-provider
reviews; named Bugbot/Security Review services or provider diversity are not claimed.
The code reviewer reported 45 focused and all 186 routing tests passing, plus 20
legacy and 20 current/parent deterministic comparisons. The security reviewer
reported all 186 routing tests, 24 additional negative checks, and 160 legacy
equivalence comparisons passing.

The coordinator independently ran the full Skills owner verifier on the tested
revision; it exited zero with `verify-skills: OK (global + local + lock +
capability-local)`. Exact current-head validation remains part of PR delivery.

## Evidence boundaries

Actual execution identity, cost, and latency were not exposed. Requested settings
are retained separately from null native acknowledgement. The native profile has
terminal completion signals but no close-agent operation; completion was observed,
and no worker-created files, processes or tools were observed. No close receipt is
invented. Observation records were persisted after results and are caller records,
not authenticated runtime attestations.

This approved synthetic screen establishes only the bounded tested operation.
Dev must independently bind the merged Skills source, exact payload, current host
bytes and qualified native profile through its governed activation transaction.
No installation, active-session migration or broader qualification is claimed.
