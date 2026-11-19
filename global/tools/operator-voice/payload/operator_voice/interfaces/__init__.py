"""Thin callers over ``OperatorVoiceService`` — CLI, stdio MCP server, skill, and intent aliases.
None of these modules touch persistence directly (build plan v3 §6); every one of them is
generated FROM ``domain.operations.OPERATIONS`` rather than hand-maintaining a second mapping."""
