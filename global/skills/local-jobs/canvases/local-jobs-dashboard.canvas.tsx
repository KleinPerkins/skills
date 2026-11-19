import {
  Stack,
  Row,
  Grid,
  H1,
  H2,
  H3,
  Text,
  Code,
  Divider,
  Pill,
  Card,
  CardHeader,
  CardBody,
  Table,
  Callout,
  Button,
  CollapsibleSection,
  UsageBar,
  Swatch,
  useHostTheme,
  useCanvasState,
  useCanvasAction,
} from "cursor/canvas";
import type { ReactNode } from "react";

type Color = "blue" | "cyan" | "gray" | "green" | "orange" | "pink" | "purple" | "yellow";

type TypeCatalogEntry = { slug: string; description: string; cardinality?: string };

type DashboardV1 = {
  schema: string;
  generated_at: string;
  run_bridge_enabled?: boolean;
  health_verdict: string;
  // The canvas renders the PM buckets (healthy / needs attention / paused / on
  // demand) it recomputes from the visible rows (see pmBuckets) so the summary
  // always reconciles with what is on screen. This mirror of dashboard.py's
  // summary is kept only for completeness / other consumers and is NOT read here.
  summary: {
    total: number;
    failing: number;
    drifted: number;
    quarantined: number;
    disabled?: number;
    on_demand?: number;
    running: number;
    unmanaged: number;
    buckets?: { healthy: number; needs_attention: number; paused: number; on_demand: number };
  };
  instances: RawInstance[];
  discovered_unmanaged: RawUnmanaged[];
  recent_runs: RawRunEvent[];
  next_actions: RawNextAction[];
  type_catalog?: TypeCatalogEntry[];
};

type RawNextAction = {
  priority: number;
  job_id: string;
  type: string;
  issue: string;
  verb: string;
  command: string;
};

type RawSchedule = {
  kind?: string;
  seconds?: number;
  hour?: number;
  minute?: number;
  run_at_load?: boolean;
  window_start_hour?: number;
  window_end_hour?: number;
  use_jitter?: boolean;
};
type RawUnmanaged = { label: string; schedule: string | RawSchedule; loaded: boolean };

type RawRunEvent = {
  ts: string;
  job_id: string | null;
  type: string;
  payload: { status: string; summary: string };
};

type NextRun = { window_start: string | null; window_end: string | null; basis: string };
type Durations = { p50: number | null; max: number | null; avg: number | null; last: number | null; series: number[] };
type RawRecent = { ts: string; status: string; summary: string | null; duration_s: number | null };
type RawLastRun = { ts: string; status: string; summary: string; duration_s: number | null } | null;

type RawExplainDeep = {
  narrative: string[];
  suggested_commands: string[];
  generated_at?: string;
  source?: "synthesize" | "agent" | string;
};

type RawInstance = {
  id: string;
  type: string;
  role: string;
  enabled: boolean;
  display_name?: string;
  description?: string;
  execution_mode?: string;
  failure_policy?: string;
  overview?: string;
  explain_deep?: RawExplainDeep;
  schedule?: unknown;
  schedule_summary?: string;
  launchd_loaded?: boolean;
  drift?: boolean;
  stale?: boolean;
  running?: boolean;
  running_since?: string | null;
  running_long?: boolean;
  next_run: NextRun;
  run_stats: {
    last_run: RawLastRun;
    consecutive_failures: number;
    durations: Durations;
    recent: RawRecent[];
  };
};

// The dashboard snapshot embedded at generation time. Read directly (NOT through
// useCanvasState) so re-running `local-jobs view` — which regenerates this file —
// always shows fresh data instead of a stale value shadowed by the sidecar.
const INITIAL_RAW = {
  "schema": "dashboard/v1",
  "generated_at": "1970-01-01T00:00:00+00:00",
  "run_bridge_enabled": false,
  "summary": {
    "total": 0,
    "failing": 0,
    "drifted": 0,
    "quarantined": 0,
    "disabled": 0,
    "on_demand": 0,
    "running": 0,
    "unmanaged": 0,
    "buckets": {
      "healthy": 0,
      "needs_attention": 0,
      "paused": 0,
      "on_demand": 0
    }
  },
  "instances": [],
  "discovered_unmanaged": [],
  "recent_events": [],
  "recent_runs": [],
  "type_catalog": [],
  "health_verdict": "No local jobs configured on this machine.",
  "next_actions": []
} as unknown as DashboardV1;

// Chat prompts for the agent-mediated actions. The canvas NEVER writes config;
// every create/rename/reschedule/mode/repair/delete is performed by the agent
// through the validated local-jobs verbs (the single safe config-writer).
const ADD_JOB_PROMPT =
  "Add a new local-jobs job on this machine. Walk me through it step by step: " +
  "(1) a human-friendly display name, (2) a one-line description of what it does, " +
  "(3) the execution mode - scheduled (runs on a timer) or on demand (runs only when I trigger it), " +
  "(4) the job type, and (5) the type-specific settings. Ground yourself first with " +
  "`scripts/local-jobs.sh describe-types` (the machine-readable type + schema list), then create it " +
  "with the validated `scripts/local-jobs.sh add-job` verb. Do not edit any config file directly.";

// Refresh writes dash.viewRequest to the sidecar when the launchd bridge is
// enabled; the bridge runs `local-jobs view` to pull live state and regenerate
// this canvas. dash.refresh also bumps a UI nonce so relative ages / staleness
// recompute immediately against the live clock (no chat, no file reads).
type RefreshState = { nonce: number; at: number };
type ViewRequestState = { nonce: string; at: number; snapshotGeneratedAt: string } | null;
type RefreshHintState = { at: number } | null;
type RunRequestState = { jobId: string; type: string; nonce: string; at: number; snapshotGeneratedAt: string } | null;
type ControlRequestState = { jobId: string; action: "pause" | "resume"; nonce: string; at: number; snapshotGeneratedAt: string } | null;
type ExplainRequestState = { jobId: string; nonce: string; at: number; snapshotGeneratedAt: string } | null;
type RunHintState = { at: number; jobId: string } | null;
type JobExplainState = { jobId: string; mode: "overview" | "full" } | null;

function normalizeJobExplain(raw: unknown): JobExplainState {
  if (!raw) return null;
  if (typeof raw === "string" && raw) return { jobId: raw, mode: "overview" };
  if (typeof raw === "object" && raw !== null && "jobId" in raw) {
    const v = raw as { jobId?: string; mode?: string };
    if (typeof v.jobId === "string" && v.jobId) {
      return { jobId: v.jobId, mode: v.mode === "full" ? "full" : "overview" };
    }
  }
  return null;
}

type GlossaryFocusState = {
  term: string | null;
  section: "summary" | "types" | null;
};

type GlossaryUiState = {
  epoch: string;
  open: boolean;
  focus: GlossaryFocusState;
};

function glossaryEpochKey(generatedAt: string, refresh: RefreshState): string {
  return `${generatedAt}|${refresh.nonce}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CALLOUT_ICON_SIZE = 16;

function InfoGlyph({ size = CALLOUT_ICON_SIZE, color }: { size?: number; color?: string }) {
  const theme = useHostTheme();
  const stroke = color ?? theme.category.cyan;
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden style={{ display: "block", flexShrink: 0 }}>
      <circle cx="8" cy="8" r="6.5" fill="none" stroke={stroke} strokeWidth="1.25" />
      <circle cx="8" cy="5.25" r="0.75" fill={stroke} />
      <path d="M8 7.25v4.25" stroke={stroke} strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  );
}

function WarningGlyph({ size = CALLOUT_ICON_SIZE }: { size?: number }) {
  const theme = useHostTheme();
  const stroke = theme.category.orange;
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden style={{ display: "block", flexShrink: 0 }}>
      <path d="M8 2.25 14.25 13H1.75Z" fill="none" stroke={stroke} strokeWidth="1.25" strokeLinejoin="round" />
      <circle cx="8" cy="10.75" r="0.75" fill={stroke} />
      <path d="M8 6.25v3" stroke={stroke} strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  );
}

function InfoCallout({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Callout tone="info" title={title} icon={<InfoGlyph />}>
      {children}
    </Callout>
  );
}

function CollapsibleCardToggle({
  open,
  onToggle,
  title,
  closedTitle,
  trailing,
}: {
  open: boolean;
  onToggle: () => void;
  title: string;
  closedTitle?: string;
  trailing?: ReactNode;
}) {
  const theme = useHostTheme();
  return (
    <Button
      variant="ghost"
      onClick={onToggle}
      style={{
        width: "100%",
        height: "auto",
        minHeight: 0,
        padding: "14px 16px",
        borderRadius: 0,
      }}
    >
      <Row align="center" gap={10} style={{ width: "100%" }}>
        <Text
          weight="semibold"
          style={{
            fontSize: 13,
            lineHeight: "16px",
            width: 14,
            flexShrink: 0,
            textAlign: "center",
            color: theme.text.secondary,
          }}
        >
          {open ? "▼" : "▶"}
        </Text>
        <Text
          weight="semibold"
          style={{
            fontSize: 15,
            lineHeight: "20px",
            flex: 1,
            minWidth: 0,
            textAlign: "left",
            color: theme.text.primary,
          }}
        >
          {open ? title : (closedTitle ?? title)}
        </Text>
        {trailing}
      </Row>
    </Button>
  );
}

// ---------------------------------------------------------------------------
// Status model — two orthogonal facets per job:
//   mode    = exactly one of Scheduled / Paused / On demand (Quarantined for a
//             broken type). "Paused" is ONLY a disabled scheduled job.
//   outcome = health of the most recent run (running / failing / ok / …).
// The summary buckets and the row pills both read from these so the numbers and
// the words always reconcile.
// ---------------------------------------------------------------------------

type Mode = "scheduled" | "paused" | "ondemand" | "error";

const MODE_META: Record<Mode, { label: string; hint: string }> = {
  scheduled: { label: "Scheduled", hint: "runs automatically on its timer" },
  paused: { label: "Paused", hint: "its timer is off — it will not run until resumed" },
  ondemand: { label: "On demand", hint: "no timer — runs only when you trigger it" },
  error: { label: "Quarantined", hint: "the job type is broken and cannot run until repaired" },
};

function modeOf(inst: RawInstance): Mode {
  if (inst.role === "error") return "error";
  if (inst.execution_mode === "on_demand") return "ondemand";
  if (inst.enabled === false) return "paused";
  return "scheduled";
}

type Outcome = "running" | "runningLong" | "failing" | "issues" | "quarantined" | "never" | "ok";

const OUTCOME_META: Record<Outcome, { label: string; color: Color }> = {
  ok: { label: "healthy", color: "green" },
  running: { label: "running", color: "blue" },
  runningLong: { label: "running long", color: "orange" },
  failing: { label: "failing", color: "pink" },
  issues: { label: "completed with issues", color: "yellow" },
  quarantined: { label: "quarantined", color: "purple" },
  never: { label: "never run", color: "gray" },
};

function outcomeOf(inst: RawInstance): Outcome {
  if (inst.role === "error") return "quarantined";
  if (inst.running) return inst.running_long ? "runningLong" : "running";
  const rs = inst.run_stats;
  // A genuine failure is always surfaced, even for on_demand jobs.
  if (rs.consecutive_failures > 0 || rs.last_run?.status === "failure") return "failing";
  // A mixed sweep is attention-worthy but not a fully-failed job.
  if (rs.last_run?.status === "completed_with_failures") return "issues";
  if (!rs.last_run) return "never";
  return "ok";
}

/** Attention = failing, mixed, quarantined, drift, or stale. NOT running-long
 *  (that is observability only) and NOT paused/on-demand (those are modes).
 *
 *  PARITY INVARIANT — must mirror lib/dashboard.py `_needs_attention`. The two
 *  agree only because lib/dashboard.py `_run_stats` guarantees
 *  `consecutive_failures >= 1` whenever the newest record's status is "failure"
 *  (its streak loop starts from the newest record), so the extra `st ===
 *  "failure"` check below is redundant-but-safe today. If you change the Python
 *  streak/status semantics, update this predicate too. The pinned parity test
 *  `test_swarm_needs_attention_parity` in bin/test-local-jobs.sh guards the
 *  Python side of this contract. */
function needsAttention(inst: RawInstance): boolean {
  if (inst.role === "error") return true;
  const rs = inst.run_stats;
  if (rs.consecutive_failures > 0) return true;
  const st = rs.last_run?.status;
  if (st === "failure" || st === "completed_with_failures") return true;
  if (inst.drift || inst.stale) return true;
  return false;
}

/** Plain-English reasons a row needs attention (folded into the row detail — the
 *  intent of the retired "Needs attention" cards section). */
function reasonList(inst: RawInstance): string[] {
  const out: string[] = [];
  if (inst.role === "error") {
    out.push("This job type is quarantined (a handler error) and cannot run until it is repaired.");
    return out;
  }
  const rs = inst.run_stats;
  const cf = rs.consecutive_failures;
  if (cf > 0) {
    out.push(`Its last ${cf === 1 ? "run" : `${cf} runs`} failed in a row.`);
  } else if (rs.last_run?.status === "failure") {
    out.push("Its most recent run failed.");
  }
  if (rs.last_run?.status === "completed_with_failures") {
    out.push("Its last multi-repo sweep finished with some repos failing while others succeeded.");
  }
  if (inst.drift) {
    out.push("Its background scheduler does not match its enabled state (drift) — a repair will realign it.");
  }
  if (inst.stale) {
    out.push("It has not recorded a success within the expected window.");
  }
  if (out.length === 0) out.push("This job needs a look.");
  return out;
}

function reasonInline(inst: RawInstance): string {
  const first = reasonList(inst)[0] ?? "it needs a look";
  return first.charAt(0).toLowerCase() + first.slice(1).replace(/\.$/, "");
}

/** A short positive line for a healthy / paused / on-demand row detail. */
function positiveReason(inst: RawInstance): string {
  const mode = modeOf(inst);
  const out = outcomeOf(inst);
  if (out === "runningLong") return "Running now — but longer than its typical duration, worth a glance.";
  if (out === "running") return "Running right now.";
  if (mode === "paused") return "Paused — its timer is off, so it will not run until you resume it.";
  if (mode === "ondemand") return "On demand — it runs only when you trigger it, so there is nothing to schedule.";
  if (out === "never") return "Configured and waiting for its first scheduled run.";
  return "On track — scheduled and succeeding on its cadence.";
}

function recentCounts(recent: RawRecent[] | undefined): { total: number; ok: number; fail: number; other: number } {
  let ok = 0;
  let fail = 0;
  let other = 0;
  const list = recent ?? [];
  for (const r of list) {
    if (r.status === "success") ok += 1;
    else if (r.status === "failure") fail += 1;
    else other += 1;
  }
  return { total: list.length, ok, fail, other };
}

function statusWord(status: string): string {
  if (status === "success") return "success";
  if (status === "failure") return "failure";
  if (status === "completed_with_failures") return "completed with issues";
  if (status === "dry-run") return "dry-run";
  return status || "unknown";
}

function formatClock12(hour: number, minute = 0): string {
  const h24 = ((hour % 24) + 24) % 24;
  const period = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 % 12 || 12;
  return `${h12}:${String(minute).padStart(2, "0")} ${period}`;
}

function formatScheduleText(text: string): string {
  return text.replace(/\b(\d{1,2}):(\d{2})\b/g, (_, h, m) => formatClock12(Number(h), Number(m)));
}

function formatIntervalLay(seconds: number): string {
  const total = Math.max(1, Math.round(seconds));
  if (total < 60) return `every ${total} seconds`;
  if (total % 86400 === 0) {
    const days = total / 86400;
    return `every ${days} ${days === 1 ? "day" : "days"}`;
  }
  if (total % 3600 === 0) {
    const hours = total / 3600;
    return `every ${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  if (total % 60 === 0) {
    const mins = total / 60;
    return `every ${mins} ${mins === 1 ? "minute" : "minutes"}`;
  }
  return `every ${formatDuration(total)}`;
}

function parseScheduleValue(schedule: unknown): RawSchedule | string | null {
  if (schedule == null) return null;
  if (typeof schedule === "object") return schedule as RawSchedule;
  if (typeof schedule === "string") {
    const trimmed = schedule.trim();
    if (trimmed.startsWith("{")) {
      try {
        return JSON.parse(trimmed) as RawSchedule;
      } catch {
        return schedule;
      }
    }
    return schedule;
  }
  return null;
}

function formatScheduleValue(schedule: unknown): string {
  const parsed = parseScheduleValue(schedule);
  if (parsed === null) return "—";
  if (typeof parsed === "string") {
    if (parsed === "inherit") return "inherits git-fetch sweep";
    return formatScheduleText(parsed);
  }
  const s = parsed;
  if (s.kind === "interval" || (typeof s.seconds === "number" && s.kind !== "calendar" && s.window_start_hour === undefined)) {
    return formatIntervalLay(s.seconds ?? 0);
  }
  if (s.kind === "calendar" || (s.hour !== undefined && s.window_start_hour === undefined)) {
    return `daily at ${formatClock12(s.hour ?? 0, s.minute ?? 0)}`;
  }
  if (s.window_start_hour !== undefined || s.kind === "window") {
    const start = s.window_start_hour ?? 18;
    const end = s.window_end_hour ?? 24;
    if (s.use_jitter === false) return `daily at ${formatClock12(start, 0)}`;
    return `daily ${formatClock12(start, 0)}–${formatClock12(end, 0)} with jitter`;
  }
  if (s.kind === "inherit") return "inherits git-fetch sweep";
  if (s.run_at_load) return "at load";
  return "scheduled";
}

function scheduleLabel(inst: RawInstance): string {
  if (inst.execution_mode === "on_demand") return "on demand (no timer)";
  if (!inst.enabled) return "schedule paused";
  if (typeof inst.schedule_summary === "string" && inst.schedule_summary) {
    return formatScheduleValue(inst.schedule_summary);
  }
  if (inst.schedule !== undefined && inst.schedule !== null) {
    return formatScheduleValue(inst.schedule);
  }
  return "inherit";
}

/** Mirrors registry._schedule_str — launchd discovery returns structured schedules. */
function formatUnmanagedSchedule(schedule: string | RawSchedule | unknown): string {
  return formatScheduleValue(schedule);
}

/** Tail of a launchd label after `<…>.local-jobs.` — works across label roots. */
function unmanagedAgentToken(label: string): string {
  const marker = ".local-jobs.";
  const idx = label.lastIndexOf(marker);
  if (idx >= 0) return label.slice(idx + marker.length);
  const parts = label.split(".");
  return parts.length >= 2 ? parts.slice(-2).join(".") : label;
}

const UNMANAGED_AGENT_HINTS: Record<string, string> = {
  "canvas-bridge":
    "Watches the local-jobs dashboard canvas folder and runs queued Run-now requests (installed by local-jobs enable-canvas-runs).",
};

function unmanagedAgentExplain(label: string): string {
  const token = unmanagedAgentToken(label);
  if (UNMANAGED_AGENT_HINTS[token]) return UNMANAGED_AGENT_HINTS[token];
  const leaf = token.split(".").pop() ?? token;
  if (UNMANAGED_AGENT_HINTS[leaf]) return UNMANAGED_AGENT_HINTS[leaf];
  if (token.startsWith("command.")) {
    return `One-off command LaunchAgent (${token}) — on disk but not registered in local-jobs.`;
  }
  return `macOS LaunchAgent (${token}) on this machine but not in your local-jobs registry — adopt if you want it managed.`;
}

function unmanagedLabelCell(label: string) {
  return (
    <Stack gap={4} style={{ minWidth: 0, maxWidth: 420 }}>
      <Code>{label}</Code>
      <Text size="small" tone="tertiary">{unmanagedAgentExplain(label)}</Text>
    </Stack>
  );
}

/** Immutable, stable identity of a job for display (never the display name). */
function jobIdLabel(inst: RawInstance): string {
  return inst.id === "__global__" ? "git-fetch sweep" : inst.id;
}

/** Human-facing name: a user-set display_name wins, else the immutable id. */
function jobName(inst: RawInstance): string {
  if (typeof inst.display_name === "string" && inst.display_name.trim()) {
    return inst.display_name.trim();
  }
  return jobIdLabel(inst);
}

function jobOverviewText(inst: RawInstance, catalog: TypeCatalogEntry[] | undefined): string {
  if (typeof inst.overview === "string" && inst.overview) return inst.overview;
  const entry = (catalog ?? []).find((t) => t.slug === inst.type);
  return entry?.description || `${jobName(inst)} is a managed ${inst.type} job on this machine.`;
}

function parseInstant(iso: string): Date | null {
  const trimmed = iso.trim();
  if (!trimmed) return null;
  const normalized = trimmed.replace(/(\.\d{3})Z$/i, "$1+00:00").replace(/Z$/i, "+00:00");
  const t = Date.parse(normalized);
  if (Number.isNaN(t)) return null;
  return new Date(t);
}

function localTime(iso: string): string {
  const d = parseInstant(iso);
  if (!d) {
    const m = iso.match(/T(\d{1,2}):(\d{2})/);
    return m ? formatClock12(Number(m[1]), Number(m[2])) : iso;
  }
  return formatClock12(d.getHours(), d.getMinutes());
}

function localDay(iso: string): string {
  const d = parseInstant(iso);
  if (!d) {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`;
    return iso;
  }
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

/** Operator-facing timestamp — local calendar day + 12h clock (matches schedule column). */
function formatTs(iso: string): string {
  if (!parseInstant(iso)) return iso;
  return `${localDay(iso)} at ${localTime(iso)}`;
}

function relAge(iso: string, nowMs: number): string {
  const d = parseInstant(iso);
  if (!d) return "";
  const secs = Math.max(0, Math.round((nowMs - d.getTime()) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function relAgeMs(tsMs: number, nowMs: number): string {
  const secs = Math.max(0, Math.round((nowMs - tsMs) / 1000));
  if (secs < 45) return "just now";
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function windowLabel(nr: NextRun): string {
  if (!nr.window_start) return "";
  const start = localTime(nr.window_start);
  if (nr.window_end && nr.window_end !== nr.window_start) {
    return `${localDay(nr.window_start)} at ${start}–${localTime(nr.window_end)}`;
  }
  return `${localDay(nr.window_start)} at ${start}`;
}

/** Short next-run phrase honoring the scheduler basis (on demand / paused / inherit). */
function nextRunLabel(inst: RawInstance): string {
  const nr = inst.next_run;
  if (nr.basis === "on_demand") return "on demand";
  if (nr.basis === "disabled") return "schedule paused";
  if (nr.basis === "inherit") return "inherits git-fetch sweep";
  return windowLabel(nr) || "—";
}

function statusColor(status: string): string {
  if (status === "success") return "#2ea043";
  if (status === "failure") return "#f85149";
  if (status === "completed_with_failures") return "#d29922";
  if (status === "dry-run") return "#8b949e";
  return "#6e7681";
}

function Sparkline({ data }: { data: number[] }) {
  const theme = useHostTheme();
  if (!data || data.length < 2) return null;
  const w = 104;
  const h = 22;
  const pad = 3;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (data.length - 1);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - 2 * pad);
  const points = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label="run duration trend">
      <polyline points={points} fill="none" stroke={theme.accent.primary} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(data.length - 1)} cy={y(data[data.length - 1])} r={2.2} fill={theme.accent.primary} />
    </svg>
  );
}

/** Enriched run-box label (M3): status + local date/time + relative age +
 *  duration + summary — surfaced as both the native tooltip and the aria-label. */
function runBoxLabel(r: RawRecent, nowMs: number): string {
  const parts: string[] = [statusWord(r.status), formatTs(r.ts)];
  const age = relAge(r.ts, nowMs);
  if (age) parts.push(age);
  if (typeof r.duration_s === "number") parts.push(`ran ${formatDuration(r.duration_s)}`);
  if (r.summary) parts.push(r.summary);
  return parts.join(" · ");
}

function HistoryStrip({ recent, nowMs }: { recent: RawRecent[]; nowMs: number }) {
  if (!recent || recent.length === 0) return <Text size="small" tone="quaternary">—</Text>;
  return (
    <Row gap={3} align="center">
      {recent.map((r, i) => {
        const label = runBoxLabel(r, nowMs);
        return (
          <span
            key={i}
            role="img"
            title={label}
            aria-label={label}
            style={{ width: 10, height: 10, borderRadius: 2, background: statusColor(r.status), display: "inline-block" }}
          />
        );
      })}
    </Row>
  );
}

function statusPill(status: string) {
  if (status === "success") return <Pill size="sm" active tone="success">success</Pill>;
  if (status === "failure") return <Pill size="sm" active tone="deleted">failure</Pill>;
  if (status === "completed_with_failures") return <Pill size="sm" active tone="warning">completed with issues</Pill>;
  if (status === "dry-run") return <Pill size="sm" tone="neutral">dry-run</Pill>;
  return <Pill size="sm" tone="neutral">—</Pill>;
}

/** Small colored dot for at-a-glance outcome scanning (color is the only signal
 *  that survives the SDK's neutral-pill styling). */
function StatusDot({ color }: { color: string }) {
  return (
    <span
      aria-hidden
      style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0, display: "inline-block" }}
    />
  );
}

function recentRunKey(run: RawRunEvent): string {
  return `${run.ts}|${run.job_id ?? ""}`;
}

const RECENT_RUN_GRID_COLS = "minmax(108px, 116px) minmax(0, 1fr) auto minmax(80px, 96px)";

function RecentRunGridHeader() {
  const theme = useHostTheme();
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: RECENT_RUN_GRID_COLS,
        columnGap: 12,
        padding: "10px 14px",
        borderBottom: `1px solid ${theme.stroke.tertiary}`,
        background: theme.fill.secondary,
        alignItems: "center",
      }}
    >
      <Text size="small" weight="semibold">When</Text>
      <Text size="small" weight="semibold">Job</Text>
      <Text size="small" weight="semibold">Status</Text>
      <Text size="small" weight="semibold" style={{ textAlign: "right" }}>
        {" "}
      </Text>
    </div>
  );
}

function RecentRunsSection({
  runs,
  instances,
  catalog,
  nowMs,
  bridgeEnabled,
  onFullExplain,
}: {
  runs: RawRunEvent[];
  instances: RawInstance[];
  catalog: TypeCatalogEntry[] | undefined;
  nowMs: number;
  bridgeEnabled: boolean;
  onFullExplain: (jobId: string) => void;
}) {
  const dispatch = useCanvasAction();
  const theme = useHostTheme();
  const [detailKey, setDetailKey] = useCanvasState<string | null>("dash.recentRunDetail", null);
  const items = runs.filter((r) => r.job_id);
  const jobById = new Map(instances.map((inst) => [inst.id, inst]));

  if (items.length === 0) return null;

  return (
    <Stack gap={8}>
      <H2>Recent runs</H2>
      <Card>
        <CardBody style={{ padding: 0 }}>
          <RecentRunGridHeader />
          <Stack gap={0}>
            {items.map((run, index) => {
              const key = recentRunKey(run);
              const open = detailKey === key;
              const inst = run.job_id ? jobById.get(run.job_id) : undefined;
              const jobDescription = inst
                ? jobOverviewText(inst, catalog)
                : `${run.job_id} is a ${run.type} job on this machine.`;
              return (
                <div key={key}>
                  {index > 0 ? <Divider /> : null}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: RECENT_RUN_GRID_COLS,
                      columnGap: 12,
                      padding: "10px 14px",
                      alignItems: "center",
                      background: open ? theme.fill.tertiary : undefined,
                    }}
                  >
                    <Text size="small" tone="secondary">{formatTs(run.ts)}</Text>
                    <Text weight="semibold" style={{ minWidth: 0 }}>
                      {run.job_id}
                    </Text>
                    {statusPill(run.payload.status)}
                    <Button
                      variant={open ? "secondary" : "ghost"}
                      onClick={() => setDetailKey(open ? null : key)}
                      style={{ justifySelf: "end" }}
                    >
                      <Row align="center" gap={5}>
                        <InfoGlyph size={14} color={open ? undefined : theme.text.link} />
                        <Text size="small" style={open ? undefined : { color: theme.text.link }}>
                          {open ? "Hide" : "Details"}
                        </Text>
                      </Row>
                    </Button>
                  </div>
                  {open ? (
                    <div style={{ padding: "0 14px 14px", background: theme.fill.tertiary }}>
                      <InfoCallout title={`What happened · ${run.job_id}`}>
                        <Stack gap={12}>
                          <Stack gap={6}>
                            <Text size="small" weight="semibold">Run outcome</Text>
                            <Row align="center" gap={8} wrap>
                              {statusPill(run.payload.status)}
                              <Text size="small" tone="tertiary">Handler · {run.type}</Text>
                            </Row>
                            <Text size="small">
                              {run.payload.summary || "No summary was recorded for this run."}
                            </Text>
                          </Stack>
                          <Divider />
                          <Stack gap={6}>
                            <Text size="small" weight="semibold">What this job does</Text>
                            <Text size="small">{jobDescription}</Text>
                          </Stack>
                          <Row gap={8} wrap>
                            <Button
                              variant="secondary"
                              disabled={!bridgeEnabled}
                              onClick={() => run.job_id && onFullExplain(run.job_id)}
                            >
                              Full explain-job
                            </Button>
                            {run.payload.status === "failure" ? (
                              <Button
                                variant="secondary"
                                onClick={() =>
                                  dispatch({
                                    type: "newComposerChat",
                                    userPrompt: `Show recent logs for local-jobs job ${run.job_id}: scripts/local-jobs.sh logs-job --id ${run.job_id} --tail 50`,
                                  })
                                }
                              >
                                View logs
                              </Button>
                            ) : null}
                          </Row>
                        </Stack>
                      </InfoCallout>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} s`;

  let rem = total;
  const days = Math.floor(rem / 86400);
  rem %= 86400;
  const hours = Math.floor(rem / 3600);
  rem %= 3600;
  const minutes = Math.floor(rem / 60);
  const secs = rem % 60;

  const parts: string[] = [];
  if (days > 0) parts.push(`${days} ${days === 1 ? "day" : "days"}`);
  if (hours > 0) parts.push(`${hours} ${hours === 1 ? "hr" : "hrs"}`);
  if (minutes > 0) parts.push(`${minutes} min`);
  if (secs > 0) parts.push(`${secs} s`);
  return parts.join(" ");
}

function durationsInline(d: Durations): string {
  const parts: string[] = [];
  if (typeof d.last === "number") parts.push(`last ${formatDuration(d.last)}`);
  if (typeof d.p50 === "number") parts.push(`typical ${formatDuration(d.p50)}`);
  return parts.length ? parts.join(" · ") : "no runs yet";
}

// ---------------------------------------------------------------------------
// Glossary — every on-screen status word has a one-line definition here.
// ---------------------------------------------------------------------------

const STATUS_WORDS: { term: string; definition: string }[] = [
  { term: "Healthy", definition: "Scheduled and succeeding on cadence (or configured and waiting for its first run)." },
  { term: "Needs attention", definition: "One or more jobs are failing, drifted, stale, quarantined, or finished a sweep with issues." },
  { term: "Paused", definition: "A scheduled job whose timer is off — it will not run until you resume it." },
  { term: "On demand", definition: "A job with no timer — it runs only when you trigger it (Run now). Never drifts or goes stale." },
  { term: "Scheduled", definition: "Runs automatically on its timer; every scheduled job shows its next local run window." },
  { term: "Running", definition: "A handler is executing this job right now." },
  { term: "Running long", definition: "Still running well past its typical duration — surfaced for visibility only; nothing is auto-killed." },
  { term: "Failing", definition: "The last run failed, or there is a streak of consecutive failures in the run log." },
  { term: "Completed with issues", definition: "A multi-repo sweep finished with mixed outcomes — some repos failed while others succeeded." },
  { term: "Never run", definition: "Configured but has not run yet on this machine." },
  { term: "Drift", definition: "A scheduled job whose launchd agent state disagrees with its enabled state — a repair realigns it." },
  { term: "Stale", definition: "A daily-scheduled job that has not recorded a success within the expected window." },
  { term: "Quarantined", definition: "A broken job type or overlay (handler error); excluded from normal operation until repaired." },
  { term: "Unmanaged", definition: "A local-jobs launch agent discovered on this Mac that is not yet adopted into the registry." },
];

function dashboardGlossary(
  instances: RawInstance[],
  catalog: TypeCatalogEntry[] | undefined,
  focus: GlossaryFocusState,
  glossaryOpen: boolean,
  onGlossaryOpenChange: (open: boolean) => void,
) {
  const theme = useHostTheme();
  const used = new Set(instances.filter((i) => i.role !== "error").map((i) => i.type));
  const typeSlugs = [...used].sort();
  const bySlug = new Map((catalog ?? []).map((t) => [t.slug, t]));
  const hasTypes = typeSlugs.length > 0;
  const totalEntries = STATUS_WORDS.length + typeSlugs.length;
  const summaryOpen = focus.section === "summary" && !!focus.term;

  return (
    <Stack gap={8}>
      <Row align="center" gap={10} style={{ width: "100%" }}>
        <InfoGlyph size={18} />
        <Stack gap={4} style={{ flex: 1, minWidth: 0 }}>
          <H2>What the labels mean</H2>
          <Text tone="secondary">
            Every status word and job type on this dashboard — click a summary count above to jump here.
          </Text>
        </Stack>
        <Pill size="md" active={glossaryOpen} title="Definitions in this glossary">
          {totalEntries} terms
        </Pill>
      </Row>
      <Card size="lg">
        <CardBody style={{ padding: 0 }}>
          <CollapsibleCardToggle
            open={glossaryOpen}
            onToggle={() => onGlossaryOpenChange(!glossaryOpen)}
            title="Full reference"
            closedTitle="Click to open the full glossary"
            trailing={
              <Pill size="sm" title="Click the header to expand definitions">
                {glossaryOpen ? "Collapse" : "Expand glossary"}
              </Pill>
            }
          />
          {glossaryOpen ? (
            <div style={{ padding: "10px 16px 16px", borderTop: `1px solid ${theme.stroke.tertiary}` }}>
              <Row align="center" gap={8} style={{ marginBottom: 4 }}>
                <InfoGlyph />
                <Text size="small" tone="tertiary">
                  Reference for the summary buckets, the status words on each job row, and the job-type names on this machine.
                </Text>
              </Row>
              <Divider style={{ marginTop: 12, marginBottom: 12 }} />
              <Stack gap={4}>
                <div key={summaryOpen ? `status-${focus.term}` : "status"}>
                <CollapsibleSection
                  title="Status words"
                  count={STATUS_WORDS.length}
                  defaultOpen={summaryOpen}
                  leading={<Swatch color="blue" style={{ width: 10, height: 10, borderRadius: 2 }} />}
                  trailing={
                    focus.term && focus.section === "summary" ? (
                      <Text size="small" tone="tertiary">Showing: {focus.term}</Text>
                    ) : (
                      <Text size="small" tone="tertiary">Healthy, Needs attention, Paused…</Text>
                    )
                  }
                >
                  <Table
                    headers={["Term", "Meaning"]}
                    rows={STATUS_WORDS.map(({ term, definition }) => [
                      <Text
                        size="small"
                        weight="semibold"
                        style={term === focus.term ? { color: theme.category.blue } : undefined}
                      >
                        {term}
                      </Text>,
                      <Text
                        size="small"
                        style={term === focus.term ? { background: theme.fill.secondary, borderRadius: 4, padding: "2px 4px" } : undefined}
                      >
                        {definition}
                      </Text>,
                    ])}
                    rowTone={STATUS_WORDS.map((g) => (g.term === focus.term ? "info" : undefined))}
                    striped
                  />
                </CollapsibleSection>
                </div>
                {hasTypes ? (
                  <CollapsibleSection
                    title="Job types on this machine"
                    count={typeSlugs.length}
                    leading={<Swatch color="purple" style={{ width: 10, height: 10, borderRadius: 2 }} />}
                    trailing={<Text size="small" tone="tertiary">{typeSlugs.join(", ")}</Text>}
                  >
                    <Table
                      headers={["Type", "What it does"]}
                      rows={typeSlugs.map((slug) => {
                        const entry = bySlug.get(slug);
                        const card = entry?.cardinality ? ` (${entry.cardinality})` : "";
                        return [
                          <Code>{slug}</Code>,
                          <Text size="small">{entry?.description ? `${entry.description}${card}` : "—"}</Text>,
                        ];
                      })}
                      striped
                    />
                  </CollapsibleSection>
                ) : null}
              </Stack>
            </div>
          ) : null}
        </CardBody>
      </Card>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Summary — PM buckets recomputed from the visible rows so counts reconcile.
// ---------------------------------------------------------------------------

type PmBuckets = { healthy: number; attention: number; paused: number; ondemand: number; total: number; running: number };

function pmBuckets(instances: RawInstance[]): PmBuckets {
  let healthy = 0;
  let attention = 0;
  let paused = 0;
  let ondemand = 0;
  let running = 0;
  for (const inst of instances) {
    if (inst.running) running += 1;
    if (needsAttention(inst)) {
      attention += 1;
      continue;
    }
    const mode = modeOf(inst);
    if (mode === "paused") paused += 1;
    else if (mode === "ondemand") ondemand += 1;
    else healthy += 1;
  }
  return { healthy, attention, paused, ondemand, total: instances.length, running };
}

type SummaryMetric = { id: string; label: string; value: number; color: Color };

function summaryMetrics(b: PmBuckets): SummaryMetric[] {
  return [
    { id: "healthy", label: "Healthy", value: b.healthy, color: "green" },
    { id: "attention", label: "Needs attention", value: b.attention, color: "orange" },
    { id: "paused", label: "Paused", value: b.paused, color: "gray" },
    { id: "ondemand", label: "On demand", value: b.ondemand, color: "blue" },
  ];
}

function summarySegments(b: PmBuckets) {
  const segments: { id: string; value: number; color: Color }[] = [];
  if (b.healthy > 0) segments.push({ id: "healthy", value: b.healthy, color: "green" });
  if (b.attention > 0) segments.push({ id: "attention", value: b.attention, color: "orange" });
  if (b.paused > 0) segments.push({ id: "paused", value: b.paused, color: "gray" });
  if (b.ondemand > 0) segments.push({ id: "ondemand", value: b.ondemand, color: "blue" });
  return segments;
}

function SummaryMetricCell({
  metric,
  highlighted,
  onSelect,
}: {
  metric: SummaryMetric;
  highlighted: boolean;
  onSelect: (term: string) => void;
  key?: string;
}) {
  const theme = useHostTheme();
  const hue = theme.category[metric.color];
  const muted = metric.value === 0 && metric.id !== "healthy";
  return (
    <Button
      variant="ghost"
      onClick={() => onSelect(metric.label)}
      style={{
        width: "100%",
        height: "auto",
        minHeight: 0,
        padding: "10px 6px 12px",
        borderRadius: 8,
        border: highlighted ? `2px solid ${hue}` : "1px solid transparent",
        background: highlighted ? theme.fill.tertiary : "transparent",
        overflow: "visible",
        boxSizing: "border-box",
      }}
    >
      <Stack gap={8} style={{ minWidth: 0, width: "100%", alignItems: "center", overflow: "visible" }}>
        <Stack gap={4} style={{ alignItems: "center", width: "100%" }}>
          <Swatch color={metric.color} style={{ width: 10, height: 10, borderRadius: 2, flexShrink: 0 }} />
          <Text
            weight="semibold"
            tone="secondary"
            style={{ fontSize: 13, lineHeight: "16px", textAlign: "center", whiteSpace: "normal", wordBreak: "break-word" }}
          >
            {metric.label}
          </Text>
        </Stack>
        <Text
          weight="semibold"
          style={{ fontSize: 20, lineHeight: "24px", color: muted ? theme.text.quaternary : hue }}
        >
          {metric.value}
        </Text>
      </Stack>
    </Button>
  );
}

function summarySection(
  buckets: PmBuckets,
  onMetricSelect: (term: string) => void,
  highlightedTerm: string | null,
) {
  const metrics = summaryMetrics(buckets);
  const segments = summarySegments(buckets);

  return (
    <Stack gap={8}>
      <Row align="center" justify="space-between" gap={10} style={{ width: "100%" }}>
        <H2>Summary</H2>
        {buckets.attention > 0 ? (
          <Pill size="sm" tone="warning">{buckets.attention} need attention</Pill>
        ) : (
          <Pill size="sm" active tone="success">all clear</Pill>
        )}
      </Row>
      <Card>
        <CardBody style={{ paddingTop: 16, paddingBottom: 16 }}>
          <Stack gap={14}>
            {buckets.total > 0 ? (
              <UsageBar
                total={buckets.total}
                segments={segments}
                topLeftLabel={
                  <Text size="small" tone="tertiary">
                    {`Each slice = share of ${buckets.total} managed job${buckets.total === 1 ? "" : "s"} by status`}
                  </Text>
                }
                topRightLabel={
                  <Text size="small" tone="tertiary">
                    {buckets.running > 0 ? `${buckets.running} running now` : "none running now"}
                  </Text>
                }
              />
            ) : null}
            <Divider />
            <Grid columns="repeat(auto-fit, minmax(104px, 1fr))" gap={10} align="start">
              {metrics.map((m) => (
                <SummaryMetricCell
                  key={m.id}
                  metric={m}
                  highlighted={highlightedTerm === m.label}
                  onSelect={onMetricSelect}
                />
              ))}
            </Grid>
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Full explain-job body (deep, bridge-backed) — rendered inline in a row detail.
// ---------------------------------------------------------------------------

function explainFullBody(
  inst: RawInstance,
  opts: {
    pending: boolean;
    bridgeEnabled: boolean;
    onRequest: () => void;
  },
) {
  const deep = inst.explain_deep;
  if (deep?.narrative?.length) {
    return (
      <Stack gap={10}>
        <Stack gap={8}>
          {deep.narrative.map((para, i) => (
            <div key={`${i}-${para.slice(0, 24)}`}><Text size="small">{para}</Text></div>
          ))}
        </Stack>
        {(deep.suggested_commands?.length ?? 0) > 0 ? (
          <Stack gap={6}>
            <Text size="small" weight="semibold">If you need to troubleshoot</Text>
            {(deep.suggested_commands ?? []).map((cmd) => (
              <div key={cmd}><Code>{cmd}</Code></div>
            ))}
          </Stack>
        ) : null}
      </Stack>
    );
  }
  if (opts.pending) {
    return (
      <Text size="small" tone="secondary">
        Inspecting this job and drafting a plain-English explanation — the bridge will refresh when ready.
      </Text>
    );
  }
  if (!opts.bridgeEnabled) {
    return (
      <Stack gap={6}>
        <Text size="small" tone="secondary">
          Run <Code>local-jobs enable-canvas-runs</Code> so Full explain-job inspects via the silent bridge.
        </Text>
      </Stack>
    );
  }
  return (
    <Stack gap={8}>
      <Text size="small" tone="secondary">
        No cached inspection yet. Tap below to queue a background inspect (reads program, config, and logs).
      </Text>
      <Button variant="secondary" onClick={opts.onRequest}>Inspect now</Button>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Inline-expand job rows — same proven pattern as Recent runs. The collapsed
// row is PM-scannable (name + outcome + mode); Details expands the full panel.
// ---------------------------------------------------------------------------

const JOB_GRID_COLS = "minmax(0, 1fr) auto auto";

type JobRowOpts = {
  nowMs: number;
  catalog?: TypeCatalogEntry[];
  bridgeEnabled: boolean;
  // Run now
  requestRun: (inst: RawInstance) => void;
  runPendingId: string | null;
  anyRunPending: boolean;
  // Pause / Resume (operational toggle via the same bridge)
  requestControl: (inst: RawInstance, action: "pause" | "resume") => void;
  controlPendingId: string | null;
  anyControlPending: boolean;
  // Shown when the bridge is not enabled
  showEnableHint: (inst: RawInstance) => void;
  // Deep explain
  jobExplain: JobExplainState;
  openFullExplain: (id: string) => void;
  requestExplain: (id: string) => void;
  setJobExplain: (v: JobExplainState) => void;
  explainPendingId: string | null;
  // Fix-in-chat command hints (from next_actions)
  fixCommandsFor: (inst: RawInstance) => string[];
};

function JobGridHeader() {
  const theme = useHostTheme();
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: JOB_GRID_COLS,
        columnGap: 12,
        padding: "10px 14px",
        borderBottom: `1px solid ${theme.stroke.tertiary}`,
        background: theme.fill.secondary,
        alignItems: "center",
      }}
    >
      <Text size="small" weight="semibold">Job</Text>
      <Text size="small" weight="semibold">Status</Text>
      <Text size="small" weight="semibold" style={{ textAlign: "right" }}>{" "}</Text>
    </div>
  );
}

function factRows(facts: [string, unknown][]) {
  return (
    <Grid columns="132px minmax(0, 1fr)" gap={8} align="start">
      {facts.map(([label, value], i) => [
        <div key={`fl-${i}`}><Text size="small" tone="tertiary">{label}</Text></div>,
        <div key={`fv-${i}`} style={{ minWidth: 0 }}>{value as any}</div>,
      ])}
    </Grid>
  );
}

function JobDetail({ inst, opts }: { inst: RawInstance; opts: JobRowOpts }) {
  const theme = useHostTheme();
  const dispatch = useCanvasAction();
  const mode = modeOf(inst);
  const attn = needsAttention(inst);
  const cliId = inst.id;
  const name = jobName(inst);
  const last = inst.run_stats.last_run;
  const counts = recentCounts(inst.run_stats.recent);
  const showDeepExplain = opts.jobExplain?.jobId === inst.id && opts.jobExplain.mode === "full";

  const facts: [string, unknown][] = [
    ["Job id", <Code>{inst.id}</Code>],
    ["Type", <Code>{inst.type}</Code>],
    ["Execution mode", <Text size="small">{MODE_META[mode].label} — {MODE_META[mode].hint}</Text>],
    ["Schedule", <Text size="small">{scheduleLabel(inst)}</Text>],
  ];
  if (mode === "scheduled") {
    facts.push(["Next run", <Text size="small">{nextRunLabel(inst)}</Text>]);
  }
  facts.push([
    "Last outcome",
    last ? (
      <Stack gap={2}>
        <Row gap={6} align="center" wrap>
          {statusPill(last.status)}
          <Text size="small" tone="tertiary">{formatTs(last.ts)} · {relAge(last.ts, opts.nowMs)}</Text>
        </Row>
        <Text size="small">{last.summary || "(no summary recorded)"}</Text>
      </Stack>
    ) : (
      <Text size="small" tone="quaternary">never run</Text>
    ),
  ]);
  facts.push([
    "Recent runs",
    counts.total > 0 ? (
      <Row gap={8} align="center" wrap>
        <Text size="small">
          {counts.total} shown · {counts.ok} ok{counts.fail ? `, ${counts.fail} failed` : ""}{counts.other ? `, ${counts.other} other` : ""}
        </Text>
        <HistoryStrip recent={inst.run_stats.recent ?? []} nowMs={opts.nowMs} />
      </Row>
    ) : (
      <Text size="small" tone="quaternary">no runs recorded yet</Text>
    ),
  ]);
  facts.push(["Durations", <Text size="small">{durationsInline(inst.run_stats.durations)}</Text>]);
  if (typeof inst.failure_policy === "string" && inst.failure_policy) {
    const policyHint =
      inst.failure_policy === "stop"
        ? "the sweep halts after the first failed repo"
        : "a failed repo does not stop the sweep";
    facts.push(["Failure policy", <Text size="small">{inst.failure_policy} — {policyHint}</Text>]);
  }

  const runnable = (inst.role === "instance" || inst.role === "global_scheduler") && !inst.running;
  const runPendingThis = opts.runPendingId === inst.id;
  const runLabel = runPendingThis
    ? "Queued for bridge…"
    : opts.bridgeEnabled
      ? (inst.enabled ? "Run now" : "Run manually")
      : "Enable runs";

  // Pause/Resume only for a scheduled instance (an on-demand job has no timer;
  // the global sweep is paused per-repo, not as a whole).
  const pausable = inst.role === "instance" && mode !== "ondemand";
  const controlPendingThis = opts.controlPendingId === inst.id;
  const controlAction: "pause" | "resume" = inst.enabled ? "pause" : "resume";
  const controlLabel = controlPendingThis
    ? "Queued for bridge…"
    : opts.bridgeEnabled
      ? (controlAction === "pause" ? "Pause" : "Resume")
      : "Enable runs";

  const manageInChat = () =>
    dispatch({
      type: "newComposerChat",
      userPrompt:
        `Manage the local-jobs job "${name}" (id: ${cliId}). I might want to rename it, change its description, ` +
        `reschedule it, switch its execution mode, pause or resume it, repair it, or delete it. Ask me which change ` +
        `I want, then make it with the validated local-jobs verbs (update-job / enable-job / disable-job / ` +
        `repair-job / delete-job) — never edit any config file directly.`,
    });
  const viewLogs = () =>
    dispatch({
      type: "newComposerChat",
      userPrompt: `Show recent logs for local-jobs job ${cliId}: scripts/local-jobs.sh logs-job --id ${cliId} --tail 50`,
    });
  const fixInChat = () => {
    const cmds = opts.fixCommandsFor(inst);
    const why = reasonInline(inst);
    const prompt = cmds.length
      ? `Fix the local-jobs job ${cliId} — ${why}. Run these and report back:\n\n${cmds.join("\n")}`
      : `The local-jobs job ${cliId} needs attention — ${why}. Investigate with ` +
        `scripts/local-jobs.sh explain-job --id ${cliId}, then fix it with the validated local-jobs verbs and report back.`;
    dispatch({ type: "newComposerChat", userPrompt: prompt });
  };

  return (
    <div style={{ padding: "0 14px 14px", background: theme.fill.tertiary }}>
      <Stack gap={12} style={{ paddingTop: 12 }}>
        {attn ? (
          <Callout tone="warning" title="Why this needs attention" icon={<WarningGlyph />}>
            <Stack gap={4}>
              {reasonList(inst).map((line, i) => (
                <div key={i}><Text size="small">{line}</Text></div>
              ))}
            </Stack>
          </Callout>
        ) : (
          <Text size="small" tone="secondary">{positiveReason(inst)}</Text>
        )}

        <Stack gap={4}>
          <Text size="small" weight="semibold">What this job does</Text>
          <Text size="small">{jobOverviewText(inst, opts.catalog)}</Text>
        </Stack>

        {factRows(facts)}

        {showDeepExplain ? (
          <Stack gap={8}>
            <Divider />
            <Text size="small" weight="semibold">Detailed explanation</Text>
            {explainFullBody(inst, {
              pending: opts.explainPendingId === inst.id,
              bridgeEnabled: opts.bridgeEnabled,
              onRequest: () => opts.requestExplain(inst.id),
            })}
            <Row>
              <Button variant="ghost" onClick={() => opts.setJobExplain(null)}>Hide detailed explanation</Button>
            </Row>
          </Stack>
        ) : null}

        <Divider />
        <Row gap={8} wrap>
          {attn ? (
            <Button
              variant="primary"
              onClick={fixInChat}
            >
              Fix in chat
            </Button>
          ) : null}
          {attn ? (
            <Button
              variant="secondary"
              disabled={!opts.bridgeEnabled}
              onClick={() => opts.openFullExplain(inst.id)}
            >
              Full explain-job
            </Button>
          ) : null}
          {attn ? (
            <Button variant="secondary" onClick={viewLogs}>View logs</Button>
          ) : null}
          {!attn ? (
            <Button
              variant="secondary"
              disabled={!opts.bridgeEnabled}
              onClick={() => opts.openFullExplain(inst.id)}
            >
              Full explain-job
            </Button>
          ) : null}
          {runnable ? (
            <Button
              variant="secondary"
              disabled={opts.bridgeEnabled && opts.anyRunPending}
              onClick={() => (opts.bridgeEnabled ? opts.requestRun(inst) : opts.showEnableHint(inst))}
            >
              {runLabel}
            </Button>
          ) : null}
          {pausable ? (
            <Button
              variant="secondary"
              disabled={opts.bridgeEnabled && opts.anyControlPending}
              onClick={() => (opts.bridgeEnabled ? opts.requestControl(inst, controlAction) : opts.showEnableHint(inst))}
            >
              {controlLabel}
            </Button>
          ) : null}
          <Button variant="ghost" onClick={manageInChat}>Manage in chat</Button>
        </Row>
      </Stack>
    </div>
  );
}

function JobRow({ inst, opts, first }: { inst: RawInstance; opts: JobRowOpts; first: boolean; key?: string }) {
  const theme = useHostTheme();
  const [open, setOpen] = useCanvasState<boolean>(`dash.jobDetail.${inst.id}`, false);
  const mode = modeOf(inst);
  const outcome = outcomeOf(inst);
  const outMeta = OUTCOME_META[outcome];
  const name = jobName(inst);
  const idLabel = jobIdLabel(inst);
  const showId = name !== idLabel;
  const last = inst.run_stats.last_run;
  const context = last
    ? `last ${statusWord(last.status)} · ${relAge(last.ts, opts.nowMs)}`
    : mode === "scheduled"
      ? `next ${nextRunLabel(inst)}`
      : scheduleLabel(inst);

  return (
    <Stack gap={0}>
      {!first ? <Divider /> : null}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: JOB_GRID_COLS,
          columnGap: 12,
          padding: "10px 14px",
          alignItems: "center",
          background: open ? theme.fill.tertiary : undefined,
        }}
      >
        <Stack gap={3} style={{ minWidth: 0 }}>
          <Row gap={6} align="center" wrap>
            <Text weight="semibold" style={{ minWidth: 0 }}>{name}</Text>
            {showId ? (
              <Text size="small" tone="tertiary" style={{ fontSize: 11, lineHeight: "14px" }}>{idLabel}</Text>
            ) : null}
          </Row>
          <Row gap={8} align="center" wrap>
            <HistoryStrip recent={inst.run_stats.recent ?? []} nowMs={opts.nowMs} />
            <Text size="small" tone="tertiary">{context}</Text>
          </Row>
        </Stack>
        <Row gap={8} align="center" wrap>
          <Row gap={5} align="center">
            <StatusDot color={theme.category[outMeta.color]} />
            <Pill size="sm" active tone={outcome === "ok" ? "success" : outcome === "failing" || outcome === "quarantined" ? "deleted" : "info"}>
              {outMeta.label}
            </Pill>
          </Row>
          {mode !== "error" ? <Pill size="sm" tone="neutral">{MODE_META[mode].label}</Pill> : null}
        </Row>
        <Button
          variant={open ? "secondary" : "ghost"}
          onClick={() => setOpen(!open)}
          style={{ justifySelf: "end" }}
        >
          <Row align="center" gap={5}>
            <InfoGlyph size={14} color={open ? undefined : theme.text.link} />
            <Text size="small" style={open ? undefined : { color: theme.text.link }}>
              {open ? "Hide" : "Details"}
            </Text>
          </Row>
        </Button>
      </div>
      {open ? <JobDetail inst={inst} opts={opts} /> : null}
    </Stack>
  );
}

function JobRowsSection({ title, count, jobs, opts }: { title: string; count?: number; jobs: RawInstance[]; opts: JobRowOpts }) {
  if (jobs.length === 0) return null;
  return (
    <Stack gap={8}>
      <Row align="center" gap={8}>
        <H2>{title}</H2>
        {typeof count === "number" ? <Pill size="sm">{count}</Pill> : null}
      </Row>
      <Card>
        <CardBody style={{ padding: 0 }}>
          <JobGridHeader />
          <Stack gap={0}>
            {jobs.map((inst, i) => (
              <JobRow key={inst.id} inst={inst} opts={opts} first={i === 0} />
            ))}
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}

type SnapshotFreshness = "live" | "recent" | "stale";

const SNAPSHOT_LIVE_MS = 15 * 60 * 1000;
const SNAPSHOT_STALE_MS = 60 * 60 * 1000;

function snapshotFreshness(ageMs: number): SnapshotFreshness {
  if (ageMs >= SNAPSHOT_STALE_MS) return "stale";
  if (ageMs < SNAPSHOT_LIVE_MS) return "live";
  return "recent";
}

/** Age used for snapshot freshness UI — rebases to the last in-canvas refresh click. */
function snapshotAgeMs(generatedAt: string, refresh: RefreshState, nowMs: number): number {
  if (refresh.nonce > 0) return Math.max(0, nowMs - refresh.at);
  const generatedMs = parseInstant(generatedAt)?.getTime() ?? Date.parse(generatedAt);
  return Math.max(0, nowMs - generatedMs);
}

function snapshotAgeLabel(generatedAt: string, refresh: RefreshState, nowMs: number): string {
  if (refresh.nonce > 0) return `viewed ${relAgeMs(refresh.at, nowMs)}`;
  return relAge(generatedAt, nowMs);
}

function isSnapshotStale(generatedAt: string, refresh: RefreshState, nowMs: number): boolean {
  return snapshotAgeMs(generatedAt, refresh, nowMs) >= SNAPSHOT_STALE_MS;
}

function HealthBadge({ hasAttention }: { hasAttention: boolean }) {
  const theme = useHostTheme();
  const color = hasAttention ? theme.category.orange : theme.category.green;
  return (
    <Row align="center" gap={8} style={{ flexShrink: 0 }}>
      <span
        title={hasAttention ? "One or more jobs need attention" : "All managed jobs look OK"}
        aria-label={hasAttention ? "Needs attention" : "Healthy"}
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: color,
          flexShrink: 0,
          display: "inline-block",
        }}
      />
      <Pill size="md" active={!hasAttention} title={hasAttention ? "One or more jobs need attention" : "All managed jobs look OK"}>
        {hasAttention ? "needs attention" : "healthy"}
      </Pill>
    </Row>
  );
}

function SnapshotFreshnessDot({
  freshness,
  refreshed,
  bridgeEnabled,
}: {
  freshness: SnapshotFreshness;
  refreshed: boolean;
  bridgeEnabled: boolean;
}) {
  const theme = useHostTheme();
  const color =
    freshness === "live" ? theme.category.green : freshness === "stale" ? theme.category.orange : theme.text.quaternary;
  const pullData = bridgeEnabled
    ? "tap Refresh to pull new run data via the canvas bridge"
    : refreshed
      ? "Refresh recomputed relative times from the embedded snapshot; run local-jobs view for new run data"
      : "tap Refresh to recompute relative times, or run local-jobs view for new run data";
  const recomputed = bridgeEnabled
    ? "View refreshed — bridge is pulling the latest run data"
    : "View refreshed — relative times recomputed from the embedded snapshot";
  const title =
    freshness === "live"
      ? refreshed
        ? recomputed
        : "Snapshot is current"
      : freshness === "stale"
        ? refreshed
          ? `View is over an hour old — ${pullData}`
          : `Snapshot is over an hour old — ${pullData}`
        : refreshed
          ? `View is aging — ${pullData}`
          : `Snapshot is aging — ${pullData}`;
  return (
    <span
      title={title}
      aria-label={title}
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
        display: "inline-block",
      }}
    />
  );
}

function SnapshotRefreshRow({
  generatedAt,
  nowMs,
  refresh,
  onRefresh,
  viewPending,
  bridgeEnabled,
}: {
  generatedAt: string;
  nowMs: number;
  refresh: RefreshState;
  onRefresh: () => void;
  viewPending: boolean;
  bridgeEnabled: boolean;
}) {
  const ageMs = snapshotAgeMs(generatedAt, refresh, nowMs);
  const freshness = snapshotFreshness(ageMs);
  const refreshed = refresh.nonce > 0;

  return (
    <Stack gap={6} style={{ width: "100%", alignItems: "flex-start" }}>
      <Row align="center" gap={8}>
        <Button
          variant={freshness === "stale" ? "primary" : "secondary"}
          onClick={onRefresh}
          disabled={viewPending}
        >
          Refresh
        </Button>
        <SnapshotFreshnessDot freshness={freshness} refreshed={refreshed} bridgeEnabled={bridgeEnabled} />
      </Row>
      <Text size="small" tone="tertiary">
        Snapshot {formatTs(generatedAt)} · {snapshotAgeLabel(generatedAt, refresh, nowMs)}
      </Text>
    </Stack>
  );
}

function DashboardHeader({
  generatedAt,
  nowMs,
  refresh,
  onRefresh,
  onAddJob,
  hasAttention,
  showHealth,
  viewPending,
  bridgeEnabled,
}: {
  generatedAt: string;
  nowMs: number;
  refresh: RefreshState;
  onRefresh: () => void;
  onAddJob: () => void;
  hasAttention: boolean;
  showHealth: boolean;
  viewPending: boolean;
  bridgeEnabled: boolean;
}) {
  return (
    <Stack gap={8} style={{ width: "100%" }}>
      <Row align="start" justify="space-between" wrap gap={12} style={{ width: "100%" }}>
        <div style={{ flex: "1 1 240px", minWidth: 0 }}>
          <H1>local-jobs monitor</H1>
        </div>
        <Row align="center" gap={10} wrap style={{ flexShrink: 0, paddingTop: 2 }}>
          <Button variant="primary" onClick={onAddJob}>
            Add job in chat
          </Button>
          {showHealth ? <HealthBadge hasAttention={hasAttention} /> : null}
        </Row>
      </Row>
      <SnapshotRefreshRow
        generatedAt={generatedAt}
        nowMs={nowMs}
        refresh={refresh}
        onRefresh={onRefresh}
        viewPending={viewPending}
        bridgeEnabled={bridgeEnabled}
      />
    </Stack>
  );
}

/** Fills the canvas panel; padding scales with viewport width. */
const DASHBOARD_ROOT_STYLE = {
  width: "100%",
  maxWidth: "100%",
  boxSizing: "border-box" as const,
  padding: "clamp(16px, 2.5vw, 28px) clamp(20px, 4vw, 40px)",
};

export default function LocalJobsDashboard() {
  const dispatch = useCanvasAction();
  const [refresh, setRefresh] = useCanvasState<RefreshState>("dash.refresh", { nonce: 0, at: 0 });
  const [viewRequest, setViewRequest] = useCanvasState<ViewRequestState>("dash.viewRequest", null);
  const [refreshHint, setRefreshHint] = useCanvasState<RefreshHintState>("dash.refreshHint", null);
  const [runRequest, setRunRequest] = useCanvasState<RunRequestState>("dash.runRequest", null);
  const [controlRequest, setControlRequest] = useCanvasState<ControlRequestState>("dash.controlRequest", null);
  const [explainRequest, setExplainRequest] = useCanvasState<ExplainRequestState>("dash.explainRequest", null);
  const [runHint, setRunHint] = useCanvasState<RunHintState>("dash.runHint", null);
  const [rawJobExplain, setRawJobExplain] = useCanvasState<unknown>("dash.jobExplain", null);
  const jobExplain = normalizeJobExplain(rawJobExplain);
  const setJobExplain = (next: JobExplainState) => setRawJobExplain(next);
  const [glossaryUi, setGlossaryUi] = useCanvasState<GlossaryUiState>("dash.glossaryUi", {
    epoch: "",
    open: false,
    focus: { term: null, section: null },
  });
  const raw = INITIAL_RAW;
  const glossaryEpoch = glossaryEpochKey(raw.generated_at, refresh);
  const glossaryOpen = glossaryUi.epoch === glossaryEpoch ? glossaryUi.open : false;
  const glossaryFocus =
    glossaryUi.epoch === glossaryEpoch ? glossaryUi.focus : { term: null, section: null };
  const nowMs = Date.now();

  const toggleSummaryGlossary = (term: string) => {
    const isSameFocused =
      glossaryOpen && glossaryFocus.section === "summary" && glossaryFocus.term === term;
    if (isSameFocused) {
      setGlossaryUi({ epoch: glossaryEpoch, open: false, focus: { term: null, section: null } });
      return;
    }
    setGlossaryUi({ epoch: glossaryEpoch, open: true, focus: { term, section: "summary" } });
  };

  const onGlossaryOpenChange = (open: boolean) => {
    setGlossaryUi({
      epoch: glossaryEpoch,
      open,
      focus: open ? glossaryFocus : { term: null, section: null },
    });
  };

  const makeNonce = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const onRefresh = () => {
    setRefresh({ nonce: refresh.nonce + 1, at: Date.now() });
    if (!raw.run_bridge_enabled) {
      setRefreshHint({ at: Date.now() });
      return;
    }
    setRefreshHint(null);
    setViewRequest({ nonce: makeNonce(), at: Date.now(), snapshotGeneratedAt: raw.generated_at });
  };
  const onAddJob = () => dispatch({ type: "newComposerChat", userPrompt: ADD_JOB_PROMPT });

  const viewSnapshotAdvanced =
    !!viewRequest && Date.parse(raw.generated_at) > Date.parse(viewRequest.snapshotGeneratedAt);
  const viewRequestFresh =
    !!raw.run_bridge_enabled &&
    !!viewRequest &&
    !viewSnapshotAdvanced &&
    nowMs - viewRequest.at < 45 * 1000;
  const snapshotAdvanced =
    !!runRequest && Date.parse(raw.generated_at) > Date.parse(runRequest.snapshotGeneratedAt);
  const runRequestFresh = !!runRequest && !snapshotAdvanced && nowMs - runRequest.at < 45 * 1000;
  const controlSnapshotAdvanced =
    !!controlRequest && Date.parse(raw.generated_at) > Date.parse(controlRequest.snapshotGeneratedAt);
  const controlRequestFresh = !!controlRequest && !controlSnapshotAdvanced && nowMs - controlRequest.at < 45 * 1000;
  const explainSnapshotAdvanced =
    !!explainRequest && Date.parse(raw.generated_at) > Date.parse(explainRequest.snapshotGeneratedAt);
  const explainRequestFresh =
    !!explainRequest && !explainSnapshotAdvanced && nowMs - explainRequest.at < 45 * 1000;

  const runPendingId = runRequestFresh ? runRequest.jobId : null;
  const controlPendingId = controlRequestFresh ? controlRequest.jobId : null;
  const explainPendingId = explainRequestFresh ? explainRequest.jobId : null;

  const requestRun = (inst: RawInstance) =>
    setRunRequest({ jobId: inst.id, type: inst.type, nonce: makeNonce(), at: Date.now(), snapshotGeneratedAt: raw.generated_at });
  const requestControl = (inst: RawInstance, action: "pause" | "resume") =>
    setControlRequest({ jobId: inst.id, action, nonce: makeNonce(), at: Date.now(), snapshotGeneratedAt: raw.generated_at });
  const requestExplain = (jobId: string) => {
    const inst = raw.instances.find((i) => i.id === jobId);
    if (inst?.explain_deep) return;
    setExplainRequest({ jobId, nonce: makeNonce(), at: Date.now(), snapshotGeneratedAt: raw.generated_at });
  };
  const openFullExplain = (jobId: string) => {
    setJobExplain({ jobId, mode: "full" });
    requestExplain(jobId);
  };
  const showEnableHint = (inst: RawInstance) => setRunHint({ at: Date.now(), jobId: inst.id });

  // Map each attention job to its precise fix commands (folds the retired
  // "Needs attention" cards into the row detail's Fix-in-chat action).
  const nextActionCommands = new Map<string, string[]>();
  for (const a of raw.next_actions) {
    const list = nextActionCommands.get(a.job_id) ?? [];
    if (a.command && !list.includes(a.command)) list.push(a.command);
    nextActionCommands.set(a.job_id, list);
  }
  const fixCommandsFor = (inst: RawInstance) => nextActionCommands.get(inst.id) ?? [];

  const jobRowOpts: JobRowOpts = {
    nowMs,
    catalog: raw.type_catalog,
    bridgeEnabled: !!raw.run_bridge_enabled,
    requestRun,
    runPendingId,
    anyRunPending: runRequestFresh,
    requestControl,
    controlPendingId,
    anyControlPending: controlRequestFresh,
    showEnableHint,
    jobExplain,
    openFullExplain,
    requestExplain,
    setJobExplain,
    explainPendingId,
    fixCommandsFor,
  };

  const staleSnapshot = isSnapshotStale(raw.generated_at, refresh, nowMs);
  const buckets = pmBuckets(raw.instances);

  const header = (
    <DashboardHeader
      generatedAt={raw.generated_at}
      nowMs={nowMs}
      refresh={refresh}
      onRefresh={onRefresh}
      onAddJob={onAddJob}
      hasAttention={buckets.attention > 0}
      showHealth={raw.instances.length > 0}
      viewPending={viewRequestFresh}
      bridgeEnabled={!!raw.run_bridge_enabled}
    />
  );

  // Empty state: no jobs configured (fresh machine or cloud). Never an error.
  if (raw.instances.length === 0) {
    return (
      <Stack gap={20} style={DASHBOARD_ROOT_STYLE}>
        {header}
        {refreshHint && !raw.run_bridge_enabled ? (
          <InfoCallout title="Enable refresh-from-canvas on this machine">
            Run <Code>scripts/local-jobs.sh enable-canvas-runs</Code>, then tap Refresh again. Until the bridge is
            enabled, Refresh only recomputes relative times from the embedded snapshot; run{" "}
            <Code>scripts/local-jobs.sh view</Code> manually for new run data.
          </InfoCallout>
        ) : null}
        <Callout tone="neutral" title="No local job data on this machine">
          No scheduled jobs are configured here — this is the empty state, nothing is wrong. Use{" "}
          <Text weight="semibold">Add job in chat</Text> above to create one through a guided chat, or run{" "}
          <Code>local-jobs add-job --type command --id &lt;id&gt; --program &lt;path&gt; --schedule HH:MM</Code>, then{" "}
          <Code>local-jobs view</Code> to see it here.
        </Callout>
      </Stack>
    );
  }

  const attentionJobs = raw.instances.filter(needsAttention);
  const otherJobs = raw.instances.filter((i) => !needsAttention(i));

  const anyRun = raw.recent_runs.length > 0 || raw.instances.some((i) => i.run_stats.last_run);

  const scheduled = raw.instances
    .filter((i) => i.next_run.window_start)
    .sort((a, b) => (a.next_run.window_start as string).localeCompare(b.next_run.window_start as string));
  const inheritors = raw.instances.filter((i) => i.next_run.basis === "inherit");

  return (
    <Stack gap={20} style={DASHBOARD_ROOT_STYLE}>
      {header}

      {staleSnapshot ? (
        <Callout tone="warning" title="Snapshot view is over an hour old" icon={<WarningGlyph />}>
          {raw.run_bridge_enabled ? (
            <>Tap Refresh to pull the latest runs via the canvas bridge.</>
          ) : (
            <>
              Tap Refresh to recompute relative times from the embedded snapshot, run{" "}
              <Code>scripts/local-jobs.sh enable-canvas-runs</Code> then Refresh again for bridge-backed pulls, or run{" "}
              <Code>local-jobs view</Code> manually for new run data.
            </>
          )}
        </Callout>
      ) : null}

      {!anyRun ? (
        <InfoCallout title="No runs recorded yet on this machine">
          These jobs are configured but have not run yet. They will appear here after the first scheduled run, or run one
          now with <Code>local-jobs run-job --id &lt;id&gt;</Code>.
        </InfoCallout>
      ) : null}

      {runHint ? (
        <InfoCallout title="Enable run-from-canvas on this machine">
          Run <Code>scripts/local-jobs.sh enable-canvas-runs</Code>, then <Code>scripts/local-jobs.sh view</Code>. Until the
          bridge is enabled, use <Code>scripts/local-jobs.sh run-job --id {runHint.jobId}</Code> (or Manage in chat).
        </InfoCallout>
      ) : null}

      {refreshHint && !raw.run_bridge_enabled ? (
        <InfoCallout title="Enable refresh-from-canvas on this machine">
          Run <Code>scripts/local-jobs.sh enable-canvas-runs</Code>, then tap Refresh again. Until the bridge is
          enabled, Refresh only recomputes relative times from the embedded snapshot; run{" "}
          <Code>scripts/local-jobs.sh view</Code> manually for new run data.
        </InfoCallout>
      ) : null}

      {viewRequestFresh ? (
        <InfoCallout title="Queued dashboard refresh">
          The canvas wrote a sidecar request and disabled Refresh while the launchd bridge runs{" "}
          <Code>local-jobs view</Code> to pull live state and regenerate this dashboard.
        </InfoCallout>
      ) : null}

      {explainRequestFresh ? (
        <InfoCallout title={`Inspecting ${explainRequest?.jobId ?? "job"} for Full explain-job`}>
          The canvas bridge is reading program, config, and logs, then will refresh this dashboard.
        </InfoCallout>
      ) : null}

      {runRequestFresh ? (
        <InfoCallout title={`Queued ${runRequest?.jobId ?? "job"} for Run now`}>
          The canvas wrote a sidecar request and disabled Run buttons while the launchd bridge picks it up. The bridge
          will regenerate the live dashboard after the run finishes or fails.
        </InfoCallout>
      ) : null}

      {controlRequestFresh ? (
        <InfoCallout title={`Queued ${controlRequest?.jobId ?? "job"} to ${controlRequest?.action === "resume" ? "resume" : "pause"}`}>
          Pause/Resume is an operational toggle: the bridge runs the validated {controlRequest?.action === "resume" ? "enable-job" : "disable-job"} verb
          (the single safe config-writer) and then regenerates this dashboard. No config is written from the canvas.
        </InfoCallout>
      ) : null}

      {summarySection(
        buckets,
        toggleSummaryGlossary,
        glossaryFocus.section === "summary" ? glossaryFocus.term : null,
      )}

      {dashboardGlossary(raw.instances, raw.type_catalog, glossaryFocus, glossaryOpen, onGlossaryOpenChange)}

      {scheduled.length > 0 ? (
        <Stack gap={8}>
          <H3>Next scheduled runs (local)</H3>
          <Row gap={8} wrap>
            {scheduled.map((j) => (
              <span key={j.id}>
                <Card>
                  <CardHeader trailing={<Pill size="sm">{j.next_run.basis}</Pill>}>{windowLabel(j.next_run)}</CardHeader>
                  <CardBody style={{ paddingTop: 8, paddingBottom: 8 }}>
                    <Text size="small" weight="semibold">{jobName(j)}</Text>
                    <Text size="small" tone="tertiary">{j.type}</Text>
                  </CardBody>
                </Card>
              </span>
            ))}
          </Row>
          {inheritors.length > 0 ? (
            <Text size="small" tone="tertiary">
              Inherits the git-fetch sweep window: {inheritors.map((i) => jobName(i)).join(", ")}
            </Text>
          ) : null}
        </Stack>
      ) : null}

      <JobRowsSection title="Attention jobs" count={attentionJobs.length} jobs={attentionJobs} opts={jobRowOpts} />

      <JobRowsSection title="Jobs" count={otherJobs.length} jobs={otherJobs} opts={jobRowOpts} />

      {raw.discovered_unmanaged.length > 0 ? (
        <Stack gap={8}>
          <Row align="center" gap={8}>
            <H2>Unmanaged agents</H2>
            <Pill size="sm">{raw.discovered_unmanaged.length}</Pill>
          </Row>
          <InfoCallout title="These launch agents are on disk but not in your local-jobs registry">
            Use Adopt to bring one under managed control, or ignore if it is intentional.
          </InfoCallout>
          <Table
            headers={["Label", "Schedule", "Loaded", "Action"]}
            rows={raw.discovered_unmanaged.map((u) => [
              unmanagedLabelCell(u.label),
              <Text size="small" tone="secondary">{formatUnmanagedSchedule(u.schedule)}</Text>,
              u.loaded ? <Pill size="sm" active tone="success">loaded</Pill> : <Pill size="sm" tone="neutral">no</Pill>,
              <Button
                variant="secondary"
                onClick={() =>
                  dispatch({
                    type: "newComposerChat",
                    userPrompt: `Adopt this launch agent into local-jobs: ${u.label}`,
                  })
                }
              >
                Adopt
              </Button>,
            ])}
          />
        </Stack>
      ) : null}

      <RecentRunsSection
        runs={raw.recent_runs}
        instances={raw.instances}
        catalog={raw.type_catalog}
        nowMs={nowMs}
        bridgeEnabled={!!raw.run_bridge_enabled}
        onFullExplain={openFullExplain}
      />
    </Stack>
  );
}
