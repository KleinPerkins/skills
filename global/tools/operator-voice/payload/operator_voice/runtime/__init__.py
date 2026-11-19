"""Runtime wiring: XDG paths, install receipts, and the top-level entrypoints (CLI/MCP/skill)
live under this package. Nothing here is imported by ``domain``/``kernel``/``persistence`` — the
dependency direction is strictly runtime -> application -> {kernel, persistence, adapters,
domain}, never the reverse (build plan v3 §4 module layout)."""
