# Codex work assessment native screen

Observed 2026-11-02 on Codex desktop 26.1027.51404 (23880).

- [Frozen fixture definitions](fixtures.json): two per difficulty band, each with predefined expected results.
- [Observed native results](native-screen.json): 16/16 checks passed; eight preferred and eight comparison runs; all workers closed.
- Requested routes: Luna/low, Sol 6.1/medium, Sol 6.1/high, Astra/high and Astra/xhigh. Actual execution identity and cost were not exposed.
- Elapsed values are upper bounds from dispatch call to observed closure and include orchestrator delay. Do not rank model latency from them.
- Workers were explicitly instructed to use no tools or external data and create no resources. Native terminal results and close receipts were observed.

The source digest binds resolver, policy and caller contract. Records are caller
observations, not signed attestations. The synthetic screen validates this bounded
operation, not general model quality, production performance or installation.
No policy activation occurred in this screen. Dev must independently bind the
merged source revision and this payload to its activation qualification record.
