---
name: agent-route
description: Enter the correct Codex project or workspace when ownership or placement is uncertain. Verify native attachment, repository identity, access and owner writer rules; use optional ecosystem search when the owner is unknown.
---

# Agent route

Use for explicit routing, uncertain ownership or a detected placement mismatch.
This skill provides Codex entry instructions. It does not run a routing service.
On another client, report unsupported and follow that client's existing owner
workflow; do not attempt Codex transitions through a leftover installed link.

## Identify the owner

1. If the repository is already named, verify that exact repository directly.
   An absent index or search dependency must not block known-project entry.
2. If ownership is unknown, use `ecosystem-search` when its source and cache are
   available. Present bounded candidates with their source and freshness.
   Ambiguous or absent matches require a focused clarification, not a guessed root.
3. Respect the owner's path and identity exclusions before access. Unknown scope
   requires resolution outside discovery. Ranking supplies no permission.

## Verify this chat

1. Inspect current native workspace information and this chat's attachments using
   the tools actually available. A cached attachment or an index location is a hint.
2. For the allowed target, verify the active workspace root, explicit command cwd,
   Git remote, Git common directory and per-worktree Git directory. Distinguish
   logical repository, clone and worktree; do not prefer a primary checkout.
3. Read the current owner's instructions and inspect branch, cleanliness and
   writer ownership. Preserve unrelated work and follow the owner's writer guard.
   Never steal a live foreign writer lease or treat a fail-open warning as exclusion.
4. Inspect the runtime's actual permission information. Placement does not establish
   write access. Unknown access stays unknown; the first necessary authorized
   mutation uses normal runtime permission handling. Never create a test file to
   manufacture permission evidence.

## Enter through the available native surface

- Reuse a suitable attached worktree when its current identity and owner state match.
- When a workspace is needed, inspect the actual native attach/create contract and
  follow owner policy and applicable authorization. Use the returned directory
  explicitly, then verify the resulting native root, cwd, Git identity and writer.
- If the current chat belongs to the wrong project and its tools cannot change that
  project, report the exact project for the operator to open. A tool that moves
  another chat does not move this one. Creating a new chat needs explicit authority.
- A shell `cd`, environment edit, filesystem link or printed helper path is not a
  native move. A successful request or returned handle alone is not a verified move.
- For a partial attachment, transport error or stale result, inspect current native
  state before reporting an outcome. Do not blindly retry or select another root.
- Denied access uses the supported permission route. Moving elsewhere is not a way
  to bypass the denial. Missing native support returns an honest operator action.

## Report the result

| Disposition | Required evidence and next action |
|---|---|
| already-correct | Native root and repository/worktree identity match; report access and writer status separately. |
| needs-workspace | Owner is known but no suitable current attachment exists; use an authorized supported transition. |
| needs-access | Root may be correct, but access is denied or unknown; use normal runtime permission handling. |
| ambiguous | Owner, target or attachment identity conflicts; clarify before an authority-sensitive action. |
| unsupported | The current host cannot perform the needed transition; name the exact operator action without claiming success. |

These are narration categories, not permission or execution tokens. A foreign writer
means stop edits in that tree and use the owner's approved separate-worktree route.
Native attachment grants no protection, registration or cleanup rights.

## Optional search dependency

Resolve this installed skill's physical directory and the same Skills source root;
verify its Git identity before resolving
`global/tools/ecosystem-index/ecosystem_index.py` there. [README](README.md) records
the source check. Copied, missing or mismatched dependencies are unavailable.
Never search recursively, assume a primary checkout, use a PATH fallback, copy a
runtime or bootstrap automatically. Known-repository entry remains available.

Search reads an existing snapshot. Refresh requires explicit bounded source-read
and metadata-storage authority; there is no automatic refresh, hook or scheduler.
Read current owner instructions before acting on any cached pointer.

Source publication, installation, native qualification, legacy retirement and
downstream distribution are separate outcomes. This skill does not clone, install,
clean up workspaces, retire old jobs or change shared settings as part of routing.
