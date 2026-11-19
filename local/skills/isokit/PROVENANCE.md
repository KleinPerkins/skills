# isokit provenance

- Upstream: <https://github.com/aadilghani1/isokit>
- Reviewed commit: `e25dfc82681628dfb5240cddc9f07081042fe348`
- Trust classification: `community`
- License: MIT; `LICENSE` is copied byte-for-byte from the reviewed commit.
- Notices: `NOTICE.md` is copied byte-for-byte from the reviewed commit.

This local Flavor-2 snapshot contains:

- `skills/isokit/**`, projected to this capability root;
- `examples/demo/src/figures/**`, kept at the same relative path so the skill's
  nearest-example instruction resolves locally;
- the upstream `LICENSE` and `NOTICE.md`.

`UPSTREAM-FILES.sha256` records every copied upstream path and its SHA-256 at the
reviewed commit. All copied bytes remain identical except the documented
`SKILL.md` routing-description adaptation and the bounded launch-diagnostic
adaptation in `scripts/shoot.mjs`. The focused capability tests reconstruct and
hash the upstream bytes for both adaptations and directly hash every other file.

The browser checker uses the upstream lock's resolved `playwright-core` release,
repinned locally to exact version `1.64.1` and its reviewed registry integrity.
The dependency is installed only into this capability's ignored `node_modules`;
no browser bundle or application-level `react-isokit` package is installed.

This snapshot does not follow the moving upstream branch. Updating it requires a
new reviewed commit pin and a deliberate capability change.
