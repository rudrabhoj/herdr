// installed by herdr
// managed by herdr; reinstalling or updating the integration overwrites this file.
// add custom hooks/plugins beside this file instead of editing it.
// HERDR_INTEGRATION_ID=pi
// HERDR_INTEGRATION_VERSION=9
// @ts-nocheck

import net from "node:net";
import path from "node:path";

const HERDR_ENV = process.env.HERDR_ENV;
const socketPath = process.env.HERDR_SOCKET_PATH;
const socketEndpoint =
  process.platform === "win32" && socketPath ? `\\\\.\\pipe\\${socketPath}` : socketPath;
const paneId = process.env.HERDR_PANE_ID;
const source = "herdr:pi";

function enabled() {
  return HERDR_ENV === "1" && !!socketPath && !!paneId;
}

function sendRequestAttempt(request: unknown, timeoutMs: number): Promise<boolean> {
  if (!enabled()) {
    return Promise.resolve(true);
  }

  return new Promise((resolve) => {
    let done = false;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const finish = (delivered: boolean) => {
      if (done) return;
      done = true;
      if (timeout) {
        clearTimeout(timeout);
      }
      socket.destroy();
      resolve(delivered);
    };

    const socket = net.createConnection(socketEndpoint!);
    socket.on("error", () => finish(false));
    socket.on("connect", () => socket.write(`${JSON.stringify(request)}\n`));
    socket.on("data", () => finish(true));
    socket.on("end", () => finish(false));
    timeout = setTimeout(() => finish(false), timeoutMs);
    timeout.unref?.();
  });
}

async function sendRequest(request: unknown): Promise<void> {
  if (await sendRequestAttempt(request, 500)) {
    return;
  }
  await sendRequestAttempt(request, 1500);
}

type AgentState = "working" | "blocked" | "idle";

type QueuedState = {
  state: AgentState;
  message?: string;
  seq: number;
};

let reportSeq = Date.now() * 1000;
let currentAgentSessionId: string | undefined;
let currentAgentSessionPath: string | undefined;

function nextReportSeq(): number {
  reportSeq += 1;
  return reportSeq;
}

function updateSessionRef(ctx: any): void {
  try {
    const file = ctx?.sessionManager?.getSessionFile?.();
    currentAgentSessionPath =
      typeof file === "string" &&
      (path.posix.isAbsolute(file) || path.win32.isAbsolute(file))
        ? file
        : undefined;
  } catch {
    currentAgentSessionPath = undefined;
  }

  try {
    const id = ctx?.sessionManager?.getSessionId?.();
    currentAgentSessionId = typeof id === "string" && id.length > 0 ? id : undefined;
  } catch {
    currentAgentSessionId = undefined;
  }
}

function withSessionRef(params: Record<string, unknown>): Record<string, unknown> {
  const resume = resumeArgv();
  const withResume = resume ? { ...params, resume_argv: resume } : params;
  if (currentAgentSessionPath) {
    return { ...withResume, agent_session_path: currentAgentSessionPath };
  }
  if (currentAgentSessionId) {
    return { ...withResume, agent_session_id: currentAgentSessionId };
  }
  return params;
}

// pi sets process.title, which wipes /proc/<pid>/cmdline, so herdr cannot read
// pi's launch flags; pi reports the restore command itself. Only flags that
// describe how to continue the same work are kept.
const RESUME_VALUE_FLAGS = new Set(["--model", "--thinking", "--provider"]);
const RESUME_SWITCHES = new Set(["--approve", "-a", "--no-approve", "-na"]);

function keptLaunchArgs(): string[] {
  const argv = process.argv.slice(2);
  const kept: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const eq = arg.indexOf("=");
    const name = eq > 0 ? arg.slice(0, eq) : arg;
    if (RESUME_VALUE_FLAGS.has(name)) {
      if (eq > 0) {
        kept.push(arg);
      } else if (i + 1 < argv.length && !argv[i + 1].startsWith("-")) {
        kept.push(arg, argv[i + 1]);
        i++;
      }
    } else if (RESUME_SWITCHES.has(arg)) {
      kept.push(arg);
    }
  }
  return kept;
}

function resumeArgv(): string[] | undefined {
  const session = currentAgentSessionPath ?? currentAgentSessionId;
  if (!session) {
    return undefined;
  }
  const argv = ["pi", ...keptLaunchArgs(), "--session", session];
  // herdr types the command into a shell and refuses these characters.
  return argv.some((arg) => arg.includes("'") || /[\u0000-\u001f]/.test(arg))
    ? undefined
    : argv;
}

// The account this pi talks to right now. Read through pi's own credential
// resolution, so extensions that switch accounts at runtime are honored.
function emailFromToken(token: unknown): string | undefined {
  if (typeof token !== "string" || token.split(".").length !== 3) {
    return undefined;
  }
  try {
    const claims = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
    const email = claims?.["https://api.openai.com/profile"]?.email ?? claims?.email;
    return typeof email === "string" && email.length > 0 ? email : undefined;
  } catch {
    return undefined;
  }
}

async function accountLabel(ctx: any): Promise<string | undefined> {
  const provider = ctx?.model?.provider;
  if (typeof provider !== "string" || provider.length === 0) {
    return undefined;
  }
  let email: string | undefined;
  try {
    const key = await Promise.race([
      ctx?.modelRegistry?.getApiKeyForProvider?.(provider),
      new Promise((resolve) => setTimeout(resolve, 1500).unref?.()),
    ]);
    email = emailFromToken(key);
  } catch {
    email = undefined;
  }
  return `pi · ${email ?? provider}`;
}

let lastAccountLabel: string | undefined;

async function reportAccount(ctx: any): Promise<void> {
  const label = await accountLabel(ctx);
  if (!label || label === lastAccountLabel) {
    return;
  }
  lastAccountLabel = label;
  await sendRequest({
    id: `${source}:metadata:${Date.now()}:${Math.random().toString(36).slice(2)}`,
    method: "pane.report_metadata",
    params: { pane_id: paneId, source, agent: "pi", display_agent: label },
  });
}

function currentSessionRef(): Record<string, unknown> | undefined {
  if (currentAgentSessionPath) {
    return { agent_session_path: currentAgentSessionPath };
  }
  if (currentAgentSessionId) {
    return { agent_session_id: currentAgentSessionId };
  }
  return undefined;
}

function reportSession(sessionStartSource?: string): Promise<void> {
  const sessionRef = currentSessionRef();
  if (!sessionRef) {
    return Promise.resolve();
  }

  return sendRequest({
    id: `${source}:session:${Date.now()}:${Math.random().toString(36).slice(2)}`,
    method: "pane.report_agent_session",
    params: {
      pane_id: paneId,
      source,
      agent: "pi",
      seq: nextReportSeq(),
      session_start_source: sessionStartSource,
      ...sessionRef,
      ...(resumeArgv() ? { resume_argv: resumeArgv() } : {}),
    },
  });
}

function sendState(state: AgentState, message?: string, seq = nextReportSeq()): Promise<void> {
  return sendRequest({
    id: `${source}:${Date.now()}:${Math.random().toString(36).slice(2)}`,
    method: "pane.report_agent",
    params: withSessionRef({
      pane_id: paneId,
      source,
      agent: "pi",
      state,
      message,
      seq,
    }),
  });
}

let sendInFlight = false;
let queuedState: QueuedState | undefined;

function queueState(state: AgentState, message?: string): void {
  queuedState = { state, message, seq: nextReportSeq() };
  if (!sendInFlight) {
    void drainStateQueue();
  }
}

async function drainStateQueue(): Promise<void> {
  if (sendInFlight) {
    return;
  }

  sendInFlight = true;
  try {
    while (queuedState) {
      const next = queuedState;
      queuedState = undefined;
      await sendState(next.state, next.message, next.seq);
    }
  } finally {
    sendInFlight = false;
    if (queuedState) {
      void drainStateQueue();
    }
  }
}

export default function (pi) {
  if (!enabled()) {
    return;
  }

  let agentActive = false;
  let blockedCount = 0;
  let blockedMessage: string | undefined;
  let lastState: AgentState | undefined;
  let lastMessage: string | undefined;
  let rootSession = false;

  function desiredState() {
    if (blockedCount > 0) {
      return { state: "blocked" as const, message: blockedMessage };
    }
    if (agentActive) {
      return { state: "working" as const, message: undefined };
    }
    return { state: "idle" as const, message: undefined };
  }

  function publishState(force = false) {
    const next = desiredState();
    if (!force && next.state === lastState && next.message === lastMessage) {
      return;
    }
    lastState = next.state;
    lastMessage = next.message;
    queueState(next.state, next.message);
  }

  pi.events.on("herdr:blocked", (data) => {
    if (!rootSession) {
      return;
    }
    if (!data?.active) {
      blockedCount = Math.max(0, blockedCount - 1);
      if (blockedCount === 0) {
        blockedMessage = undefined;
      }
      publishState();
      return;
    }

    blockedCount += 1;
    blockedMessage = data.label;
    publishState();
  });

  pi.on("session_start", async (event, ctx) => {
    // TUI only: RPC/JSON/print modes are headless (no PTY herdr can display),
    // and RPC still reports hasUI=true, so mode is the reliable gate.
    if (ctx?.mode !== "tui") {
      return;
    }
    rootSession = true;
    updateSessionRef(ctx);
    await reportSession(event?.reason);
    // A reload can replace this extension mid-run without emitting another agent_start.
    agentActive = ctx?.isIdle?.() === false;
    publishState(true);
    void reportAccount(ctx);
  });

  pi.on("model_select", (_event, ctx) => {
    if (!rootSession) {
      return;
    }
    void reportAccount(ctx);
  });

  pi.on("agent_start", (_event, ctx) => {
    if (!rootSession) {
      return;
    }
    updateSessionRef(ctx);
    void reportSession();
    agentActive = true;
    publishState();
    void reportAccount(ctx);
  });

  pi.on("agent_settled", (_event, ctx) => {
    if (!rootSession || ctx?.isIdle?.() !== true) {
      return;
    }

    agentActive = false;
    publishState();
  });
}
