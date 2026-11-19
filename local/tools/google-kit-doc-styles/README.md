# google-kit Doc Styles Local Bootstrap

Local-only bootstrap data for google-kit document style profiles.

This artifact is private to Laurence's machine setup. It ships a generic blank-slate style profile template plus a Laurence-local placeholder seed that contains no private document IDs, font choices, or other captured style bytes.

## Installed Shape

`install.sh` writes missing seed profiles into:

```text
${GOOGLE_KIT_CONFIG_DIR:-$HOME/Library/Application Support/google-kit}/doc-styles/
```

Existing valid profiles are preserved. Missing profiles are written atomically with `0600` file permissions under a `0700` directory. If a destination seed file is corrupt, the installer quarantines that file before restoring the seed.

## Files

- `templates/blank-style-profile.json` is the generic starter template.
- `profiles/laurence/default.json` is Laurence's local placeholder seed until a real profile is captured from an existing Google Doc.

Both shipped profiles are unbound starters: source/template document references
are null and named styles are empty. The Laurence placeholder also leaves the
document style empty. Fresh installation does not carry captured font, margin,
tab, timestamp or document-reference data from another machine. Existing valid
local profiles are preserved byte-for-byte unless `--force` is explicitly used.
For preservation-sensitive setup, use `--no-repair` to leave invalid existing
profiles unchanged as well.

This is a local data bootstrap. It performs no Google request, OAuth operation,
MCP registration or client activation. Actual style capture/application and live
writer qualification belong to the consuming provider's owner workflow. An empty
starter is not a captured style profile or authoring acceptance.

Run `python3 -B -m unittest discover -s local/tools/google-kit-doc-styles -p 'test_install.py' -v`
for the shipped-data contract and disposable installer checks. The tests use an
isolated config directory, never a live account or the operator's profiles.
