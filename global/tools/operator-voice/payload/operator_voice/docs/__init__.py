"""Deterministic documentation generation — build plan v3 §6: "One typed operation registry
generates CLI commands, MCP tools, JSON schemas, operation cards, examples, error taxonomy,
posture annotations, and deterministic help." Every module here is a pure function of the
registries in ``domain.operations``/``domain.contracts`` and produces byte-identical output for
byte-identical input (§6.3 "rebuilt ... and must be byte-stable")."""
