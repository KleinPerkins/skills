"""Typed, versioned prompt registry — build plan v3 §6 ("Resources and prompts are not inferred
from operation names. They live in separate typed, versioned registries") + §13 M2 worklist 2
("full resources/prompts/generated docs").

Each :class:`PromptSpec` is a small, operator-data-free authoring scaffold: it renders to one or
more MCP prompt messages that tell a host agent WHICH read/mutation operations to call and in what
order, using only argument placeholders the caller supplies at request time. A prompt NEVER embeds
profile values, raw samples, keys, or paths — it is a static template plus caller-supplied argument
names, exactly like the resource registry's redaction guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass

PROMPTS_VERSION = "prompts/v2"


@dataclass(frozen=True)
class PromptArg:
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class PromptSpec:
    name: str
    description: str
    tier: str  # "m1" | "m2"
    arguments: tuple[PromptArg, ...] = ()
    template: str = ""  # rendered with str.format(**arguments); missing optionals default to ""

    def render(self, arguments: dict[str, str] | None = None) -> str:
        supplied = dict(arguments or {})
        for arg in self.arguments:
            if arg.required and not supplied.get(arg.name):
                raise KeyError(f"prompt {self.name!r} requires argument {arg.name!r}")
            supplied.setdefault(arg.name, "")
        return self.template.format(**supplied)


PROMPTS: tuple[PromptSpec, ...] = (
    PromptSpec(
        name="voice-matched-draft",
        description="Draft text in the operator's calibrated voice for one context, then mechanically validate it.",
        tier="m2",
        arguments=(
            PromptArg("subject_id", "The OPERATOR subject to draft as"),
            PromptArg("consumer_id", "Allowlisted consumer identifier for the bundle request"),
            PromptArg("task", "Plain-language description of what to write"),
            PromptArg("channel", "Delivery channel (e.g. email, chat)", required=False),
            PromptArg("audience", "Who it is for (e.g. team, exec)", required=False),
        ),
        template=(
            "You are drafting in the operator's own voice. Do NOT invent facts.\n"
            "1. Call `context.get` with subject_id={subject_id}, consumer_id={consumer_id}, "
            "channel={channel}, audience={audience} to fetch a VoiceContextBundle/v1.\n"
            "2. If the bundle `abstained` is true or confidence is low, say so and ask for more input "
            "instead of guessing.\n"
            "3. Write the draft for this task, honoring the bundle's ranked facts and instructions "
            "(register/tone, preferred/banned lexicon, structure, sentence targets): {task}\n"
            "4. Call `draft.validate` with the finished draft (set semantic=true for a high-stakes "
            "draft) and report any failed checks verbatim before delivering."
        ),
    ),
    PromptSpec(
        name="correct-my-voice",
        description="Record a direct operator correction so it outranks anything OVT inferred.",
        tier="m2",
        arguments=(
            PromptArg("subject_id", "The OPERATOR subject being corrected"),
            PromptArg("correction", "What the operator said is wrong, in their own words"),
        ),
        template=(
            "The operator is correcting their voice profile. Direct feedback always wins over "
            "inference.\n"
            "1. Call `feedback.add` with subject_id={subject_id} and the operator's exact words: "
            "\"{correction}\".\n"
            "2. If it names a specific facet to change, follow up with `fact.correct` for that "
            "facet/scope. Never overwrite silently — confirm what changed."
        ),
    ),
    PromptSpec(
        name="external-subject-brief",
        description="Produce an analysis-only insight brief for an enrolled EXTERNAL subject (never authoring).",
        tier="m2",
        arguments=(
            PromptArg("subject_id", "An enrolled EXTERNAL subject id"),
            PromptArg("purpose", "The approved analysis purpose"),
        ),
        template=(
            "This is analysis ONLY. OVT will not and must not produce authoring instructions or a "
            "VoiceContextBundle for an EXTERNAL subject.\n"
            "1. Call `subject.insights` with subject_id={subject_id}, purpose={purpose}.\n"
            "2. Present the evidence-bounded observations with their uncertainty and counter-evidence. "
            "Do NOT use them to ghost-write as this person."
        ),
    ),
)

PROMPTS_BY_NAME: dict[str, PromptSpec] = {p.name: p for p in PROMPTS}


def get_prompt(name: str) -> PromptSpec:
    spec = PROMPTS_BY_NAME.get(name)
    if spec is None:
        raise KeyError(f"unknown prompt: {name!r}")
    return spec


def render_prompt_messages(name: str, arguments: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Return MCP-shaped prompt messages (a single user turn) for ``name``. Deterministic and
    operator-data-free — only the caller's supplied argument values ever appear."""
    spec = get_prompt(name)
    return [{"role": "user", "content": spec.render(arguments)}]


def render_prompts_md() -> str:
    lines = ["<!-- GENERATED by operator_voice.docs.prompts — do not hand-edit. -->\n",
             "# OVT MCP prompts\n"]
    lines.append(
        "Authoring scaffolds derived from the typed prompt registry. Each renders to a single user "
        "message that directs a host agent to the right operations; none embeds operator data.\n"
    )
    for spec in PROMPTS:
        lines.append(f"## `{spec.name}` ({spec.tier})\n")
        lines.append(f"{spec.description}\n")
        if spec.arguments:
            lines.append("| argument | required | description |")
            lines.append("|---|---|---|")
            for a in spec.arguments:
                lines.append(f"| `{a.name}` | {'yes' if a.required else 'no'} | {a.description} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "PromptArg",
    "PromptSpec",
    "PROMPTS",
    "PROMPTS_BY_NAME",
    "PROMPTS_VERSION",
    "get_prompt",
    "render_prompt_messages",
    "render_prompts_md",
]
