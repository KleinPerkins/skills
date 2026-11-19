---
name: capability
description: "Help non-technical operators view, add, update, remove, or repair AI capabilities—skills, agents, rules, tools, or plugins—in plain language. Use to inspect, discover, install, enable, create, configure, share, validate, or fix tooling across Cursor, Claude, Codex, and GitHub Copilot."
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Capability playbook

You are operating capabilities **on behalf of someone who never sees the plumbing**. They think in
outcomes — "add this", "share it", "is it working?", "fix it". They should never have to learn the
words `lock`, `reconcile`, `expose`, `shelf`, `manifest`, `symlink`, or `parity`. Your job is to run
one dependable loop over whatever capability commands *this* environment provides, and to report back
in their language.

This skill is **environment-agnostic**. It does not name any specific repo, tool, or command. Discover
the capability commands your current workspace offers (a create/add verb, a share/publish verb, a
sync/repair verb, and a health/doctor view), then bind the loop below to them. If a step has no verb
here, do the equivalent safe action and say so.

## The one loop (run this every time)

1. **Hear the intent.** Restate what they want as an outcome, in their words.
2. **Confirm back — in plain language, before acting.** Say what you are about to do and the few
   choices you inferred ("I'll add a skill called *weekly-report*, just for you, available in your
   editor"). Proceed unless they correct you. Only pause for a *genuine* decision (see Escalate).
3. **Act through the environment's own verbs.** Use the workspace's create / share / sync / health
   commands — never hand-edit plumbing, never invent file surgery. One verb per intent.
4. **Verify the real outcome.** Do not report success from a command's exit code alone. Check the
   thing they actually care about: *is it live in their tools? did it reach the team?* Use the
   environment's health/doctor view to confirm the real state.
5. **Narrate plainly.** Tell them the outcome in their words: "Done — it's live in your editor now,"
   or "It's shared; teammates get it next time they sync." One health verdict, at most one next step.
6. **Self-repair.** If verification shows it is present-but-not-active, or a transient command failed,
   run the environment's repair/sync verb once and re-verify before bothering them. Fix what you can.
7. **Escalate only real decisions.** Surface a choice to the owner *only* when it is a product call,
   irreversible, or involves a secret (see Escalate). Everything mechanical, you handle.

## Speak their language (vocabulary map)

Translate system state into outcomes. Never echo the raw term on the left to the owner.

| What the system reports | What you tell the owner |
| --- | --- |
| installed / symlinked / surfaced in a tool home | "live in your editor / assistant on this computer" |
| published / merged / vendored to the shared copy | "shared with your team — they get it on their next sync" |
| present but not linked / not reconciled | "set up, but not switched on yet — I'll fix it now" |
| waiting on review / required check / approval | "almost there — waiting on a quick teammate sign-off" |
| lock parity OK / in sync | "saved and consistent" |
| drift / diverged / out of sync | "your copy and the team's don't match — I'll sort it out" |
| not vendored / no payload yet | "not on your computer yet — the team is still publishing it" |

When the environment's health view returns a verdict, map it straight through:

- **Ready** → "It's live."
- **Ready-but-degraded** → "It's working in some of your tools; I'll switch it on everywhere."
- **Needs repair** → "It's not active yet — I can fix that," then run the repair verb.

## Safe defaults (infer; don't interrogate)

Pick sensible defaults from the intent and *state them in the confirm-back*. Re-decide only if the
owner reacts.

- **Kind** — infer from what they describe: a reusable instruction/checklist → a *skill*; a background
  helper → an *agent*; an always-on guideline → a *rule*; a script/binary → a *tool*; an IDE or
  marketplace extension with its own runtime → a *plugin*.
- **Scope** — default to **just them** unless they say "the team," "everyone," or "share." Sharing is
  the one genuinely product-shaped choice — see Escalate.
- **Where it shows up** — default to the tools they actually use (their editor first). Don't ask which
  assistants to enable; enable the obvious ones and mention it.
- **Name** — derive a clear, lowercase, hyphenated name from their description; confirm it in passing.

The bar: ask **at most one** question, and only if it is a real product choice. Everything else is a
default you state and move past.

## Escalate ONLY these (otherwise: act)

Bring a decision to the owner only when it is genuinely one of:

1. **A product choice** — "just you, or the whole team?"; which of two real options they want; anything
   that changes what the capability *is* or who it affects.
2. **Irreversible** — deleting/replacing something others may rely on; anything you cannot cleanly undo.
3. **A secret** — a token, key, password, or private credential is involved.

If it is none of these, it is mechanical: **do it, then narrate it.** "It said *diverged*, now what?"
is not a decision to hand back — it is a repair to run.

## Verify before you claim success

The most common failure is reporting "done" when the outcome isn't real. Always close the loop:

- After **add/create**: confirm it is *live in their tools on this computer* — via the health view, not
  just the create command's output.
- After **share/publish**: confirm it *reached the shared copy / is on its way* (merged, or queued
  behind a named sign-off you name plainly). Don't claim "the team has it" while it's still pending.
- After **repair/sync**: re-run the health view and confirm the verdict flipped to Ready.

If verification fails, self-repair once (step 6) and re-verify before escalating.

## Report format

Keep it to a few plain lines:

```
What you asked: <their outcome, their words>
What I did:     <the one verb, in plain language>
Status:         <Ready / working-on-it / waiting on <named sign-off>>
Live for you:   <yes — in <tools> / not yet — <one next step>>
```

If something needs the owner, end with exactly one question framed as a product choice — never as
jargon.

## Quick mode

For a clearly-scoped ask ("add X just for me"), collapse to: confirm-back in one line → run the verb →
verify via the health view → one-line outcome ("Done — *X* is live in your editor."). No checklist, no
plumbing, no extra questions.

## Guardrails

- Read/confirm/act/verify/narrate/repair — in that order. Never claim success without verification.
- Use the environment's own verbs; never hand-edit lock/manifest/symlink plumbing.
- Default to the owner's private scope; treat sharing as the one product choice worth a question.
- Escalate only product / irreversible / secret decisions. Everything else, you handle and narrate.
