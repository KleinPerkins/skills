# continual-learning-consolidate

Small standard-library consolidator for the machine-local global agent-memory
projection.

## Data flow

1. `~/agent-learnings.md` is the explicit home seed.
2. `agent-route map --json` supplies the only candidate root list.
3. The consolidator reads `agent-learnings.md` only at those exact roots.
4. The admission firewall keeps the home seed plus corroborated cross-root
   memory, while work-only and one-off workspace memory stays local.
5. `memory.py` conservatively deduplicates and scans the final projection.
6. The validated bytes atomically replace `~/AGENTS.md`.

`~/AGENTS.md` is output-only: its prior contents never participate in the
projection. The runtime has no git, GitHub, registry, YAML, or network
dependency.

## Layout

```text
continual-learning-consolidate/
├── SKILL.md
├── README.md
├── install.sh
├── meta.yml
├── scripts/
│   ├── continual_learning_consolidate.py
│   └── lib/memory.py
└── tests/
    ├── integration_install.sh
    ├── run_tests.sh
    └── test_consolidator.py
```

`install.sh` publishes a content-addressed runtime under
`~/.local/share/continual-learning-consolidate/`, exposes
`~/.local/bin/continual-learning-consolidate`, and idempotently ensures the
09:00 local job. `--no-schedule` installs only the runtime.

## Verify

```bash
bash tests/run_tests.sh
```

The suite covers admission, same-origin clone rejection, parse and scanner
fail-closed behavior, output-only semantics, idempotence, the zero-git/zero-gh
process boundary, conservative near-duplicate handling, and hermetic install.
