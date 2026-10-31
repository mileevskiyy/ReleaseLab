import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  Plus,
  Check,
  CheckCircle2,
  X,
  AlertTriangle,
  GitCommitHorizontal,
  Package,
  Layers,
  ShieldCheck,
  Clock3,
  RotateCcw,
  Download,
  Play,
  ChevronRight,
  ChevronDown,
  Terminal,
  ArrowLeft,
  FileCode2,
  Activity,
  Server,
  RefreshCw,
  LockKeyhole,
  Minus,
  SquareArrowOutUpRight,
} from "lucide-react";
const time = (n: number) =>
  new Date(n).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
const short = (v: string) => v.slice(0, 12);
const active = (op: any) =>
  ["queued", "running", "verifying"].includes(op.state);
const passed = (r: any) =>
  r.evidence.length > 0 &&
  Object.values(r.evidence.at(-1).checks).every((v) => v === "passed");
function Logo() {
  return (
    <span className="logo">
      <span>
        R<span>↗</span>
      </span>
      release<span>lab</span>
      <sup>/ 08</sup>
    </span>
  );
}
function Badge({
  state,
  children,
}: {
  state: string;
  children?: React.ReactNode;
}) {
  return (
    <span className={"badge " + state}>
      <i />
      {children || state.replace("_", " ")}
    </span>
  );
}
function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={wide ? "wide" : ""}
      onCancel={close}
      aria-label={title}
    >
      <div className="modal-head">
        <span className="mono">RELEASELAB / SANDBOX</span>
        <button className="icon" onClick={close} aria-label="Close dialog">
          <X size={19} />
        </button>
      </div>
      <h2>{title}</h2>
      {children}
    </dialog>
  );
}
export default function App() {
  const [w, setW] = useState<any>(null),
    [csrf, setCsrf] = useState(""),
    [ready, setReady] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [view, setView] = useState("releases"),
    [selected, setSelected] = useState(""),
    [tab, setTab] = useState("overview"),
    [modal, setModal] = useState<any>(null);
  const pending = useRef(new Map<string, string>()),
    latestRevision = useRef(-1);
  async function request(
    path: string,
    method = "GET",
    body?: any,
    token = csrf,
  ) {
    const response = await fetch("/api" + path, {
      method,
      headers: { "Content-Type": "application/json", "x-csrf-token": token },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        setW(null);
        setCsrf("");
        latestRevision.current = -1;
      }
      const e = new Error(data.error || "Request failed.") as Error & {
        status?: number;
      };
      e.status = response.status;
      throw e;
    }
    return data;
  }
  function accept(data: any) {
    if (data.revision < latestRevision.current) return;
    latestRevision.current = data.revision;
    setW(data);
    setSelected(
      (old) =>
        old ||
        data.releases.find((r: any) => r.manifest.version === "1.5.0")?.id ||
        data.releases[0]?.id ||
        "",
    );
  }
  async function refresh(token = csrf) {
    accept(await request("/workspace", "GET", undefined, token));
  }
  async function run(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function command(path: string, body: any) {
    const sig = JSON.stringify({ path, body });
    const key = pending.current.get(sig) || crypto.randomUUID();
    pending.current.set(sig, key);
    try {
      const data = await request(path, "POST", { ...body, request_id: key });
      pending.current.delete(sig);
      accept(data.workspace);
      return data;
    } catch (e) {
      if ((e as any).status && (e as any).status < 500)
        pending.current.delete(sig);
      throw e;
    }
  }
  useEffect(() => {
    (async () => {
      try {
        const s = await request("/session");
        if (s.authenticated) {
          setCsrf(s.csrf);
          await refresh(s.csrf);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setReady(true);
      }
    })();
  }, []);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(t);
    }
  }, [notice]);
  async function start(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const name = String(new FormData(e.currentTarget).get("name"));
    await run(async () => {
      const s = await request("/demo", "POST", { name });
      setCsrf(s.csrf);
      latestRevision.current = -1;
      await refresh(s.csrf);
    });
  }
  const find = (id: string) => w?.releases.find((r: any) => r.id === id);
  function openQueue(r: any, env: string) {
    setModal({
      kind: "queue",
      release: r,
      env,
      generation: w.environments[env].generation,
    });
  }
  async function advance(op: any, step: string, healthy?: boolean) {
    await run(async () => {
      const result = await command(`/operations/${op.id}/advance`, {
        version: op.version,
        step,
        ...(healthy === undefined
          ? {}
          : {
              healthy,
              note: healthy
                ? "Manually reported healthy for this sandbox run."
                : "Manually reported unhealthy for this sandbox run.",
            }),
      });
      const updated = result.workspace.operations.find(
        (o: any) => o.id === op.id,
      );
      setNotice(
        updated.state === "failed"
          ? "Rehearsal stopped. The active environment was preserved."
          : updated.state === "succeeded"
            ? "Sandbox pointer updated. The journal records the change."
            : "Sandbox operation advanced.",
      );
    });
  }
  async function create(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    await run(async () => {
      const dependencies = String(fd.get("dependencies") || "")
        .split("\n")
        .map((v) => v.trim())
        .filter(Boolean)
        .map((v) => {
          const split = v.lastIndexOf("@");
          if (split <= 0)
            throw new Error("Write each dependency as name@1.2.3.");
          return { name: v.slice(0, split), version: v.slice(split + 1) };
        });
      const migration = String(fd.get("migration") || "").trim();
      const manifest = {
        service: "atlas-api",
        version: String(fd.get("version")),
        source_commit: String(fd.get("commit")),
        build_ref: String(fd.get("build")),
        dependencies,
        migrations: migration
          ? [
              {
                name: migration,
                backward_compatible: fd.get("compatible") === "on",
              },
            ]
          : [],
        config_keys: String(fd.get("config") || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const r = await command("/releases", {
        manifest,
        notes: String(fd.get("notes")),
      });
      setSelected(r.release_id);
      setView("releases");
      setTab("overview");
      setModal(null);
      setNotice("Candidate registered. Its manifest is now immutable.");
    });
  }
  if (!ready)
    return (
      <div className="loading">
        <Logo />
        <p>Initializing your release workspace…</p>
      </div>
    );
  if (!w)
    return (
      <div className="landing">
        <header>
          <Logo />
          <span className="mono">A LITTLE MORE CERTAINTY.</span>
        </header>
        <main className="landing-grid">
          <div className="landing-copy">
            <span className="eyebrow">
              <i />
              RELEASE ENGINEERING / REHEARSED
            </span>
            <h1>
              Know what’s
              <br />
              going out.
              <br />
              <em>
                And how to
                <br />
                bring it back.
              </em>
            </h1>
            <p>
              Trace the candidate. Check the gates. Rehearse the next step.
              <br />A working release-control sandbox, from manifest to restore.
            </p>
            <form onSubmit={start}>
              <label>
                Your operator name
                <input
                  name="name"
                  defaultValue="Demo operator"
                  minLength={2}
                  maxLength={30}
                  required
                />
              </label>
              <button className="primary large" disabled={busy}>
                {busy ? "Initializing…" : "Open the sandbox"}
                <ArrowUpRight size={18} />
              </button>
            </form>
            <div className="landing-note">
              <Terminal size={14} />
              <span>
                Simulated environments. Recorded checks. No external
                infrastructure changes.
              </span>
            </div>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
          </div>
          <div className="release-paper" aria-hidden="true">
            <div className="paper-top">
              <span>RELEASE / 0015</span>
              <span className="paper-status">READY FOR REVIEW</span>
            </div>
            <div className="paper-version">
              <span>ATLAS-API</span>
              <strong>
                v1.5.0<span>↗</span>
              </strong>
              <small>ONE MANIFEST. ONE TRACEABLE IDENTITY.</small>
            </div>
            <div className="paper-route">
              {[
                ["01", "MANIFEST", "REGISTERED"],
                ["02", "CHECKS", "RECORDED"],
                ["03", "STAGING", "VERIFIED"],
                ["04", "PRODUCTION", "AWAITING SIGN-OFF"],
              ].map(([n, t, s]) => (
                <div key={n}>
                  <span>{n}</span>
                  <strong>{t}</strong>
                  <small>{s}</small>
                  <i>{n === "04" ? "○" : "✓"}</i>
                </div>
              ))}
            </div>
            <div className="paper-bottom">
              <span>SHA256 / a21e8c…</span>
              <span>SANDBOX RECORD</span>
            </div>
            <div className="paper-stamp">
              REHEARSE
              <br />
              <strong>BEFORE RELEASE.</strong>
            </div>
          </div>
        </main>
        <div className="landing-strip">
          <div>
            <Package size={17} />
            <span>Immutable manifests.</span>
          </div>
          <div>
            <ShieldCheck size={17} />
            <span>Gates that enforce the rules.</span>
          </div>
          <div>
            <RotateCcw size={17} />
            <span>A history you can restore from.</span>
          </div>
        </div>
        <footer>
          Disposable demo · One service, two simulated environments · No CI
          execution or real deployments
        </footer>
      </div>
    );
  const r = find(selected) || w.releases[0],
    evidence = r?.evidence.at(-1),
    approval = r?.approvals.at(-1),
    stage = w.environments.staging,
    prod = w.environments.production,
    isStage = r?.id === stage.release_id,
    isProd = r?.id === prod.release_id,
    approvalValid = Boolean(
      approval &&
        evidence &&
        approval.evidence_id === evidence.id &&
        approval.expires_at >= w.now,
    ),
    currentOp = modal?.operationId
      ? w.operations.find((o: any) => o.id === modal.operationId)
      : null;
  const envBusy = (env: string) =>
    w.operations.some((o: any) => o.environment === env && active(o));
  const canPromote = (candidate: any, env: string) =>
    candidate.gates[env].every((g: any) => g.ok) && !envBusy(env);
  const history = (env: string) =>
    w.operations
      .filter(
        (o: any) =>
          o.environment === env &&
          o.state === "succeeded" &&
          o.release_id !== w.environments[env].release_id &&
          o.sequence <
            (w.operations.find(
              (p: any) => p.id === w.environments[env].operation_id,
            )?.sequence || 0),
      )
      .sort((a: any, b: any) => b.sequence - a.sequence);
  function envCard(env: string, compact = false) {
    const current = w.environments[env],
      candidate = find(current.release_id),
      op = w.operations.find((o: any) => o.environment === env && active(o));
    return (
      <section
        key={env}
        className={"env-card " + env + (compact ? " compact" : "")}
      >
        <div className="env-card-top">
          <span>
            <i />
            {env}
          </span>
          <span className="mono">SANDBOX</span>
        </div>
        <div className="env-version">
          <strong>v{candidate?.manifest.version || "—"}</strong>
          <Badge state={op ? "running" : "succeeded"}>
            {op ? op.state : "active"}
          </Badge>
        </div>
        <p className="digest">sha256:{short(current.digest || "")}</p>
        <div className="env-meta">
          <span>
            Generation <strong>{current.generation}</strong>
          </span>
          <span>{time(current.updated_at)} UTC</span>
        </div>
        {op ? (
          <button
            className="env-action"
            onClick={() => setModal({ kind: "operation", operationId: op.id })}
          >
            Open rehearsal #{String(op.sequence).padStart(3, "0")}
            <ArrowRight size={14} />
          </button>
        ) : (
          <button
            className="env-action"
            disabled={!history(env).length}
            onClick={() =>
              setModal({
                kind: "restore",
                env,
                generation: current.generation,
                targets: history(env),
              })
            }
          >
            <RotateCcw size={13} />
            Restore from history
            <ArrowUpRight size={13} />
          </button>
        )}
      </section>
    );
  }
  function opTable(ops: any[]) {
    return (
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>RUN / TYPE</th>
              <th>CANDIDATE</th>
              <th>ENVIRONMENT</th>
              <th>STATE</th>
              <th>RECORDED</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ops.map((op) => (
              <tr key={op.id}>
                <td>
                  <span className="run-id">
                    #{String(op.sequence).padStart(3, "0")}
                  </span>
                  <span className="table-type">
                    {op.kind === "restore" ? "RESTORE" : "PROMOTION"}
                    {op.sample && <small>SAMPLE</small>}
                  </span>
                </td>
                <td>
                  <strong className="table-version">
                    v{find(op.release_id)?.manifest.version}
                  </strong>
                  <small className="table-digest">{short(op.digest)}</small>
                </td>
                <td>
                  <span className={"env-name " + op.environment}>
                    <i />
                    {op.environment}
                  </span>
                </td>
                <td>
                  <Badge state={op.state} />
                </td>
                <td className="table-time">{time(op.updated_at)} UTC</td>
                <td>
                  <button
                    className="icon"
                    aria-label={`Open rehearsal ${op.sequence}`}
                    onClick={() =>
                      setModal({ kind: "operation", operationId: op.id })
                    }
                  >
                    <ArrowUpRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!ops.length && (
          <div className="empty">No rehearsals for this candidate yet.</div>
        )}
      </div>
    );
  }
  return (
    <div className="app">
      <header className="app-header">
        <button
          className="brand"
          onClick={() => setView("releases")}
          aria-label="ReleaseLab home"
        >
          <Logo />
        </button>
        <span className="service-label">
          <span>/</span> atlas-api <ChevronDown size={11} />
        </span>
        <nav aria-label="Workspace navigation">
          {[
            ["releases", "Releases"],
            ["environments", "Environments"],
            ["audit", "Audit log"],
          ].map(([v, t]) => (
            <button
              key={v}
              aria-label={t}
              className={view === v ? "selected" : ""}
              onClick={() => setView(v)}
            >
              {t}
            </button>
          ))}
        </nav>
        <div className="header-right">
          <span className="operator-dot" />
          <span>{w.actor}</span>
          <button
            className="icon"
            aria-label="Refresh workspace"
            disabled={busy}
            onClick={() => run(() => refresh())}
          >
            <RefreshCw size={15} />
          </button>
        </div>
      </header>
      <div className="sandbox-bar">
        <span>
          <Terminal size={13} />
          <strong>REHEARSAL MODE</strong>
        </span>
        <p>
          Checks and health signals are recorded manually. No external
          repositories or environments are changed.
        </p>
        <span className="mono">LOCAL ADAPTER / ACTIVE</span>
      </div>
      <main>
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            <button
              onClick={() =>
                run(async () => {
                  await refresh();
                  setError("");
                })
              }
            >
              Reload latest
            </button>
            <button
              className="icon"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={15} />
            </button>
          </div>
        )}
        {notice && (
          <div className="toast" role="status">
            <CheckCircle2 size={17} />
            {notice}
          </div>
        )}
        {view === "releases" && (
          <div className="release-layout">
            <aside className="release-index">
              <div className="index-heading">
                <span className="eyebrow">
                  CANDIDATES / {String(w.releases.length).padStart(2, "0")}
                </span>
                <button
                  className="icon"
                  aria-label="New candidate"
                  onClick={() => setModal({ kind: "create" })}
                >
                  <Plus size={17} />
                </button>
              </div>
              <div className="release-list">
                {[...w.releases].reverse().map((candidate: any) => {
                  const production = prod.release_id === candidate.id,
                    staging = stage.release_id === candidate.id,
                    fail = !passed(candidate);
                  return (
                    <button
                      key={candidate.id}
                      aria-label={`Open release v${candidate.manifest.version}`}
                      className={r.id === candidate.id ? "active" : ""}
                      onClick={() => {
                        setSelected(candidate.id);
                        setTab("overview");
                      }}
                    >
                      <span
                        className={
                          "candidate-dot " +
                          (production
                            ? "live"
                            : staging
                              ? "staging"
                              : fail
                                ? "failed"
                                : "draft")
                        }
                      />
                      <div>
                        <strong>v{candidate.manifest.version}</strong>
                        <small>
                          {production
                            ? "ACTIVE IN PRODUCTION"
                            : staging
                              ? "ACTIVE IN STAGING"
                              : fail
                                ? "CHECKS NEED ATTENTION"
                                : "REGISTERED CANDIDATE"}
                        </small>
                      </div>
                      <ChevronRight size={12} />
                    </button>
                  );
                })}
              </div>
              <button
                className="new-candidate"
                disabled={w.releases.length >= 25}
                onClick={() => setModal({ kind: "create" })}
              >
                <Plus size={14} />
                Register candidate
              </button>
              <div className="index-footnote">
                <LockKeyhole size={17} />
                <p>
                  A candidate’s manifest stays fixed. New content means a new
                  version.
                </p>
              </div>
            </aside>
            <section className="release-workbench">
              <div className="candidate-heading">
                <div>
                  <span className="eyebrow">ATLAS-API / RELEASE CANDIDATE</span>
                  <h1>
                    v{r.manifest.version}
                    <span>
                      {isProd
                        ? "PRODUCTION"
                        : isStage
                          ? "STAGING"
                          : "CANDIDATE"}
                    </span>
                  </h1>
                  <p>{r.notes}</p>
                </div>
                {r.sample && <span className="sample-tag">SAMPLE FIXTURE</span>}
              </div>
              <div className="candidate-meta">
                <span>
                  <GitCommitHorizontal size={13} />
                  {r.manifest.source_commit.slice(0, 8)}
                </span>
                <span>
                  <Package size={12} />
                  {r.manifest.build_ref}
                </span>
                <span>
                  <Clock3 size={12} />
                  {time(r.created_at)} UTC
                </span>
              </div>
              <div className="candidate-tabs">
                {[
                  ["overview", "Readiness"],
                  ["manifest", "Manifest"],
                  ["history", "Rehearsals"],
                ].map(([v, t]) => (
                  <button
                    key={v}
                    className={tab === v ? "active" : ""}
                    onClick={() => setTab(v)}
                  >
                    {t}
                    {v === "history" && (
                      <span>
                        {
                          w.operations.filter((o: any) => o.release_id === r.id)
                            .length
                        }
                      </span>
                    )}
                  </button>
                ))}
                <a href={`/api/releases/${r.id}/export`}>
                  <Download size={12} />
                  Evidence JSON
                </a>
              </div>
              {tab === "overview" && (
                <>
                  <div className="route">
                    <div className="route-line" />
                    {[
                      ["01", "MANIFEST", true],
                      ["02", "CHECKS", passed(r)],
                      ["03", "STAGING", isStage],
                      ["04", "SIGN-OFF", approvalValid],
                      ["05", "PRODUCTION", isProd],
                    ].map(([n, t, ok]) => (
                      <div
                        key={String(n)}
                        className={
                          "route-step " + (ok ? "complete" : "pending")
                        }
                      >
                        <span>{ok ? <Check size={13} /> : n}</span>
                        <strong>{t}</strong>
                        <small>{ok ? "RECORDED" : "WAITING"}</small>
                      </div>
                    ))}
                  </div>
                  <section className="panel evidence-panel">
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">BUILD EVIDENCE</span>
                        <h2>
                          Trust the record.
                          <br />
                          Know its source.
                        </h2>
                      </div>
                      <button
                        className="secondary"
                        onClick={() =>
                          setModal({ kind: "evidence", release: r })
                        }
                      >
                        <Plus size={13} />
                        Record evidence
                      </button>
                    </div>
                    <div className="evidence-source">
                      <span className="source-label">
                        {evidence?.sample
                          ? "SAMPLE FIXTURE"
                          : evidence
                            ? "MANUAL SANDBOX RECORD"
                            : "NO EVIDENCE"}
                      </span>
                      <p>
                        {evidence
                          ? "These outcomes were recorded, not executed by ReleaseLab."
                          : "Register unit, API and security outcomes for this manifest."}
                      </p>
                    </div>
                    <div className="check-list">
                      {[
                        ["unit", "Unit tests"],
                        ["api", "API contract"],
                        ["security", "Security review"],
                      ].map(([key, label]) => (
                        <div key={key}>
                          <span>
                            {evidence?.checks[key] === "passed" ? (
                              <CheckCircle2 size={15} />
                            ) : (
                              <AlertTriangle size={15} />
                            )}
                            <strong>{label}</strong>
                          </span>
                          <Badge state={evidence?.checks[key] || "pending"} />
                        </div>
                      ))}
                    </div>
                    {evidence && (
                      <div className="evidence-note">
                        <p>{evidence.note}</p>
                        <span>
                          {evidence.actor} · {time(evidence.at)} UTC · valid for
                          60 minutes
                        </span>
                      </div>
                    )}
                  </section>
                  <section className="panel approval-panel">
                    <div>
                      <span className="eyebrow">PRODUCTION SIGN-OFF</span>
                      <h2>
                        {approvalValid
                          ? "A deliberate yes."
                          : "One deliberate next step."}
                      </h2>
                      <p>
                        {approvalValid
                          ? `Recorded by ${approval.actor}. Tied to this manifest and the latest evidence.`
                          : "After staging, record a sign-off for this exact manifest and evidence set."}
                      </p>
                    </div>
                    <button
                      className={approvalValid ? "signed" : "primary"}
                      disabled={busy || approvalValid || !r.can_approve}
                      onClick={() => setModal({ kind: "approve", release: r })}
                    >
                      {approvalValid ? (
                        <>
                          <Check size={15} />
                          Signed off
                        </>
                      ) : (
                        <>
                          Record sign-off
                          <ArrowRight size={14} />
                        </>
                      )}
                    </button>
                    {approvalValid && (
                      <span className="approval-expiry">
                        Expires {time(approval.expires_at)} UTC
                      </span>
                    )}
                  </section>
                  <section className="gates-section">
                    <div className="section-heading">
                      <span className="eyebrow">
                        PROMOTION GATES / PRODUCTION
                      </span>
                      <span className="mono">EVALUATED ON THE SERVER</span>
                    </div>
                    {r.gates.production.map((g: any) => (
                      <div
                        className={"gate-row " + (g.ok ? "pass" : "blocked")}
                        key={g.key}
                      >
                        <span>
                          {g.ok ? <Check size={13} /> : <Minus size={13} />}
                        </span>
                        <div>
                          <strong>{g.label}</strong>
                          <small>{g.detail}</small>
                        </div>
                        <span className="mono">{g.ok ? "PASS" : "HOLD"}</span>
                      </div>
                    ))}
                  </section>
                </>
              )}
              {tab === "manifest" && (
                <>
                  <section className="panel manifest-panel">
                    <div className="panel-heading">
                      <div>
                        <span className="eyebrow">CONTENT IDENTITY</span>
                        <h2>
                          One manifest.
                          <br />
                          One fixed digest.
                        </h2>
                      </div>
                      <LockKeyhole size={21} />
                    </div>
                    <label className="digest-label">
                      SHA-256 of the manifest
                      <input
                        aria-label="Manifest SHA-256"
                        readOnly
                        value={r.digest}
                        onFocus={(e) => e.target.select()}
                      />
                    </label>
                    <pre>{JSON.stringify(r.manifest, null, 2)}</pre>
                    <p className="technical-note">
                      This digest identifies canonical manifest JSON, not a
                      container image or binary. Source/build fields are
                      recorded metadata; no repository is fetched.
                    </p>
                  </section>
                  <section className="panel comparison-panel">
                    <span className="eyebrow">
                      COMPARE WITH ACTIVE PRODUCTION
                    </span>
                    <h2>
                      What changes from v
                      {find(prod.release_id)?.manifest.version}?
                    </h2>
                    {[
                      "version",
                      "source_commit",
                      "build_ref",
                      "dependencies",
                      "migrations",
                      "config_keys",
                    ].map((key) => {
                      const base = JSON.stringify(
                          find(prod.release_id)?.manifest[key],
                        ),
                        next = JSON.stringify(r.manifest[key]),
                        changed = base !== next;
                      return (
                        <div
                          key={key}
                          className={"diff-row " + (changed ? "changed" : "")}
                        >
                          <span>{changed ? "+" : "="}</span>
                          <div>
                            <strong>{key}</strong>
                            <code>{changed ? next : "Unchanged"}</code>
                          </div>
                        </div>
                      );
                    })}
                  </section>
                </>
              )}
              {tab === "history" && (
                <section className="panel history-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">RELEASE JOURNAL</span>
                      <h2>Every attempted step.</h2>
                    </div>
                  </div>
                  {opTable(
                    [...w.operations]
                      .filter((o: any) => o.release_id === r.id)
                      .reverse(),
                  )}
                </section>
              )}
            </section>
            <aside className="environment-rail">
              <div className="rail-heading">
                <span className="eyebrow">ENVIRONMENT POINTERS</span>
                <span>02</span>
              </div>
              {envCard("staging", true)}
              {envCard("production", true)}
              <section className="next-step">
                <span className="eyebrow">NEXT / REHEARSE A PROMOTION</span>
                <h3>
                  Make the next move
                  <br />
                  an informed one.
                </h3>
                <button
                  className="secondary"
                  disabled={busy || !canPromote(r, "staging")}
                  onClick={() => openQueue(r, "staging")}
                >
                  Queue staging rehearsal
                  <ArrowRight size={13} />
                </button>
                <button
                  className="primary"
                  disabled={busy || !canPromote(r, "production")}
                  onClick={() => openQueue(r, "production")}
                >
                  Queue production rehearsal
                  <ArrowRight size={13} />
                </button>
                <p>
                  Active pointers change only after a healthy sandbox outcome. A
                  failed run preserves the previous version.
                </p>
              </section>
            </aside>
          </div>
        )}
        {view === "environments" && (
          <div className="full-view">
            <div className="page-heading">
              <div>
                <span className="eyebrow">
                  ATLAS-API / ENVIRONMENT REGISTER
                </span>
                <h1>
                  Know what’s active.
                  <br />
                  <em>Keep the way back.</em>
                </h1>
                <p>
                  Two simulated environments. Generation-checked changes. A
                  traceable history.
                </p>
              </div>
              <span className="outline-stamp">
                SANDBOX
                <br />
                <strong>NO EXTERNAL DEPLOY</strong>
              </span>
            </div>
            <div className="environments-grid">
              {envCard("staging")}
              {envCard("production")}
            </div>
            <section className="panel all-history">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">DEPLOYMENT & RESTORE JOURNAL</span>
                  <h2>A history, not a guess.</h2>
                </div>
                <span className="mono">{w.operations.length} RECORDS</span>
              </div>
              {opTable([...w.operations].reverse())}
            </section>
            <div className="restore-note">
              <RotateCcw size={18} />
              <p>
                Restore selects a prior successful artifact snapshot for that
                environment. It changes only the sandbox pointer; it does not
                reverse database migrations or real infrastructure.
              </p>
            </div>
          </div>
        )}
        {view === "audit" && (
          <div className="full-view">
            <div className="page-heading">
              <div>
                <span className="eyebrow">ATLAS-API / AUDIT LOG</span>
                <h1>
                  A record of
                  <br />
                  <em>deliberate changes.</em>
                </h1>
                <p>
                  Latest 200 commands with before/after environment snapshots.
                  Seed fixtures do not add fictional audit activity.
                </p>
              </div>
              <span className="audit-count">
                {w.events.length}
                <small>RECORDED EVENTS</small>
              </span>
            </div>
            <div className="audit-list">
              {[...w.events].reverse().map((event: any) => (
                <article key={event.id}>
                  <span className="event-id">
                    {String(event.id).padStart(3, "0")}
                  </span>
                  <div>
                    <div className="audit-event-top">
                      <span>{event.kind}</span>
                      <small>{time(event.at)} UTC</small>
                    </div>
                    <h3>{event.text}</h3>
                    <p>{event.detail}</p>
                    <div className="audit-env-diff">
                      {["staging", "production"].map((env) => (
                        <span key={env}>
                          <i className={env} />
                          {env}: gen {event.before[env].generation} →{" "}
                          {event.after[env].generation}
                        </span>
                      ))}
                    </div>
                    <span className="audit-actor">
                      Recorded by {event.actor}
                    </span>
                  </div>
                </article>
              ))}
              {!w.events.length && (
                <div className="empty audit-empty">
                  <Activity size={30} />
                  <h2>The next command starts the record.</h2>
                  <p>Record evidence, sign off or queue a rehearsal.</p>
                </div>
              )}
            </div>
          </div>
        )}
        <footer className="app-footer">
          <span className="mono">
            RELEASELAB / CONFIDENCE BEFORE THE NEXT STEP.
          </span>
          <span>Demo data resets on restart or after 24h of inactivity.</span>
          <span className="mono">
            REV {String(w.revision).padStart(3, "0")}
          </span>
        </footer>
      </main>
      {modal && (
        <Modal
          key={
            modal.kind + (modal.release?.id || "") + (modal.operationId || "")
          }
          title={
            modal.kind === "create"
              ? "Register a candidate"
              : modal.kind === "evidence"
                ? "Record build evidence"
                : modal.kind === "approve"
                  ? "Record a production sign-off"
                  : modal.kind === "queue"
                    ? `Queue ${modal.env} rehearsal`
                    : modal.kind === "restore"
                      ? "Restore from successful history"
                      : modal.kind === "cancel"
                        ? "Cancel this rehearsal?"
                        : `Rehearsal #${String(currentOp?.sequence || 0).padStart(3, "0")}`
          }
          wide={modal.kind === "create" || modal.kind === "operation"}
          close={() => {
            if (!busy) {
              setModal(null);
              setError("");
            }
          }}
        >
          {modal.kind === "create" && (
            <form onSubmit={create}>
              <p className="form-hint">
                Register metadata for an immutable candidate. These fields do
                not fetch a repository or build an image.
              </p>
              <div className="form-grid">
                <label>
                  Version
                  <input
                    name="version"
                    defaultValue="1.7.0"
                    maxLength={20}
                    required
                    pattern="(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})"
                  />
                </label>
                <label>
                  Build reference
                  <input
                    name="build"
                    required
                    maxLength={80}
                    defaultValue="manual-build-17"
                  />
                </label>
              </div>
              <label>
                Recorded source commit
                <input
                  name="commit"
                  defaultValue={"a".repeat(40)}
                  pattern="[0-9a-f]{40}"
                  minLength={40}
                  maxLength={40}
                  required
                />
              </label>
              <label>
                Release notes
                <textarea
                  name="notes"
                  rows={3}
                  maxLength={1500}
                  required
                  placeholder="What changes, and what should a reviewer look for?"
                />
              </label>
              <details className="manifest-extras">
                <summary>
                  Dependencies, config keys and migrations
                  <ChevronDown size={14} />
                </summary>
                <label>
                  Dependencies <small>(one name@1.2.3 per line)</small>
                  <textarea
                    name="dependencies"
                    rows={3}
                    defaultValue="core-runtime@3.2.1"
                  />
                </label>
                <label>
                  Configuration key names{" "}
                  <small>(comma separated, no secret values)</small>
                  <input
                    name="config"
                    defaultValue="LOG_LEVEL, REQUEST_TIMEOUT"
                  />
                </label>
                <label>
                  Migration name <small>(optional)</small>
                  <input
                    name="migration"
                    maxLength={60}
                    placeholder="add_history_index"
                  />
                </label>
                <label className="checkbox">
                  <input type="checkbox" name="compatible" defaultChecked />
                  <span>This declared migration is backward compatible</span>
                </label>
              </details>
              <div className="form-actions">
                <button className="primary" disabled={busy}>
                  Register candidate
                  <ArrowRight size={15} />
                </button>
              </div>
            </form>
          )}
          {modal.kind === "evidence" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                void run(async () => {
                  await command(`/releases/${modal.release.id}/evidence`, {
                    version: modal.release.version,
                    unit: String(fd.get("unit")),
                    api: String(fd.get("api")),
                    security: String(fd.get("security")),
                    note: String(fd.get("note")),
                  });
                  setModal(null);
                  setNotice(
                    "Evidence recorded. Previous sign-offs no longer apply to the new evidence.",
                  );
                });
              }}
            >
              <p className="form-hint">
                You are recording sandbox outcomes for v
                {modal.release.manifest.version}. ReleaseLab does not execute
                these tests or a security scanner.
              </p>
              {[
                ["unit", "Unit tests"],
                ["api", "API contract"],
                ["security", "Security review"],
              ].map(([key, label]) => (
                <label className="evidence-input" key={key}>
                  {label}
                  <select
                    name={key}
                    aria-label={label + " outcome"}
                    defaultValue="passed"
                  >
                    <option value="passed">Passed — recorded outcome</option>
                    <option value="failed">Failed — recorded outcome</option>
                  </select>
                </label>
              ))}
              <label>
                Evidence note
                <textarea
                  name="note"
                  rows={3}
                  minLength={5}
                  maxLength={400}
                  required
                  defaultValue="Recorded during a sandbox release rehearsal."
                />
              </label>
              <p className="form-hint">
                Evidence expires after 60 minutes. Recording a new set
                invalidates earlier sign-offs and gate snapshots.
              </p>
              <div className="form-actions">
                <button className="primary" disabled={busy}>
                  Record evidence
                  <Check size={15} />
                </button>
              </div>
            </form>
          )}
          {modal.kind === "approve" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const note = String(new FormData(e.currentTarget).get("note"));
                void run(async () => {
                  await command(`/releases/${modal.release.id}/approve`, {
                    version: modal.release.version,
                    note,
                  });
                  setModal(null);
                  setNotice(
                    "Sign-off recorded for the current manifest and evidence.",
                  );
                });
              }}
            >
              <p className="form-hint">
                Record a single-operator sandbox sign-off for v
                {modal.release.manifest.version}. This is an audit record, not
                independent approval or a cryptographic signature.
              </p>
              <div className="approval-summary">
                <span>OPERATOR</span>
                <strong>{w.actor}</strong>
                <span>MANIFEST SHA-256</span>
                <code>{modal.release.digest}</code>
              </div>
              <label>
                Review note
                <textarea
                  name="note"
                  minLength={10}
                  maxLength={400}
                  rows={3}
                  required
                  defaultValue="Reviewed the recorded evidence and staging candidate for this sandbox rehearsal."
                />
              </label>
              <div className="form-actions">
                <button className="primary" disabled={busy}>
                  Record sign-off
                  <ShieldCheck size={15} />
                </button>
              </div>
            </form>
          )}
          {modal.kind === "queue" && (
            <>
              <p className="form-hint">
                Queue v{modal.release.manifest.version} for the simulated{" "}
                {modal.env} environment. The current artifact stays active until
                a healthy outcome is reported.
              </p>
              <div className="queue-summary">
                <span>TARGET GENERATION</span>
                <strong>
                  {modal.generation} → {modal.generation + 1}
                </strong>
                <span>MANIFEST</span>
                <code>{short(modal.release.digest)}</code>
              </div>
              <p className="form-hint">
                Gates are checked now and again while advancing. No external
                service is deployed.
              </p>
              <div className="form-actions">
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const result = await command("/operations", {
                        release_id: modal.release.id,
                        environment: modal.env,
                        generation: modal.generation,
                      });
                      setModal({
                        kind: "operation",
                        operationId: result.operation_id,
                      });
                      setNotice("Sandbox rehearsal queued.");
                    })
                  }
                >
                  Queue rehearsal
                  <ArrowRight size={15} />
                </button>
              </div>
            </>
          )}
          {modal.kind === "operation" && currentOp && (
            <>
              <div className="operation-summary">
                <Badge state={currentOp.state} />
                <span className={"env-name " + currentOp.environment}>
                  <i />
                  {currentOp.environment}
                </span>
                <span className="mono">
                  {currentOp.kind === "restore" ? "RESTORE" : "PROMOTION"} ·
                  SANDBOX
                </span>
                {currentOp.sample && <span className="sample-tag">SAMPLE</span>}
              </div>
              <h3 className="operation-version">
                v{find(currentOp.release_id)?.manifest.version}
                <span>sha256:{short(currentOp.digest)}</span>
              </h3>
              <div className="operation-steps">
                {currentOp.steps.map((s: any, i: number) => (
                  <div key={i} className={"operation-step " + s.state}>
                    <span>
                      {s.state === "succeeded" ? (
                        <Check size={13} />
                      ) : (
                        String(i + 1).padStart(2, "0")
                      )}
                    </span>
                    <div>
                      <strong>{s.state}</strong>
                      <p>{s.note}</p>
                    </div>
                    <small>
                      {new Date(s.at).toLocaleTimeString("en-GB", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        timeZone: "UTC",
                      })}
                    </small>
                  </div>
                ))}
              </div>
              {currentOp.failure && (
                <div className="operation-failure">
                  <AlertTriangle size={17} />
                  <div>
                    <strong>Active environment preserved.</strong>
                    <p>{currentOp.failure}</p>
                  </div>
                </div>
              )}
              {currentOp.state === "succeeded" && (
                <div className="operation-success">
                  <CheckCircle2 size={17} />
                  <p>
                    Sandbox artifact pointer committed. See the environment
                    register and audit snapshot.
                  </p>
                </div>
              )}
              {currentOp.reason && (
                <p className="operation-reason">Reason: {currentOp.reason}</p>
              )}
              {active(currentOp) && (
                <div className="operation-controls">
                  <p>
                    {currentOp.state === "queued"
                      ? "Start the local sandbox adapter."
                      : currentOp.state === "running"
                        ? "Proceed to a manually reported health outcome."
                        : "Choose a synthetic health outcome. No network probe is run."}
                  </p>
                  <div>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() =>
                        setModal({ kind: "cancel", operation: currentOp })
                      }
                    >
                      Cancel rehearsal
                    </button>
                    {currentOp.state === "queued" && (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => advance(currentOp, "start")}
                      >
                        <Play size={13} />
                        Start sandbox run
                      </button>
                    )}
                    {currentOp.state === "running" && (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => advance(currentOp, "verify")}
                      >
                        Begin health verification
                        <ArrowRight size={14} />
                      </button>
                    )}
                    {currentOp.state === "verifying" && (
                      <>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() => advance(currentOp, "health", false)}
                        >
                          Report failing health
                          <X size={13} />
                        </button>
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() => advance(currentOp, "health", true)}
                        >
                          Report healthy
                          <Check size={13} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          {modal.kind === "restore" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const fd = new FormData(e.currentTarget);
                void run(async () => {
                  const result = await command("/restores", {
                    target_operation_id: String(fd.get("target")),
                    environment: modal.env,
                    generation: modal.generation,
                    reason: String(fd.get("reason")),
                  });
                  setModal({
                    kind: "operation",
                    operationId: result.operation_id,
                  });
                  setNotice("Restore rehearsal queued.");
                });
              }}
            >
              <p className="form-hint">
                Select an earlier successful snapshot in {modal.env}. Restore
                bypasses fresh build/sign-off gates and requires a recorded
                reason. It never reverses real data or schema changes.
              </p>
              <label>
                Successful deployment
                <select
                  name="target"
                  aria-label="Successful deployment"
                  required
                >
                  {modal.targets.map((o: any) => (
                    <option key={o.id} value={o.id}>
                      #{String(o.sequence).padStart(3, "0")} · v
                      {find(o.release_id)?.manifest.version}
                      {o.sample ? " · sample fixture" : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Restore reason
                <textarea
                  name="reason"
                  rows={3}
                  minLength={10}
                  maxLength={400}
                  required
                  defaultValue="Rehearse restoring the previous successful artifact after reviewing the release."
                />
              </label>
              <div className="form-actions">
                <button className="primary" disabled={busy}>
                  Queue restore rehearsal
                  <RotateCcw size={14} />
                </button>
              </div>
            </form>
          )}
          {modal.kind === "cancel" && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const note = String(new FormData(e.currentTarget).get("note"));
                void run(async () => {
                  const result = await command(
                    `/operations/${modal.operation.id}/advance`,
                    { version: modal.operation.version, step: "cancel", note },
                  );
                  setModal({
                    kind: "operation",
                    operationId: modal.operation.id,
                  });
                  setNotice(
                    "Rehearsal cancelled. The active environment was preserved.",
                  );
                });
              }}
            >
              <label>
                Cancellation reason
                <textarea
                  name="note"
                  rows={3}
                  minLength={10}
                  maxLength={400}
                  required
                  defaultValue="No longer needed after reviewing the sandbox release plan."
                />
              </label>
              <div className="form-actions">
                <button className="danger" disabled={busy}>
                  Cancel rehearsal
                  <X size={14} />
                </button>
              </div>
            </form>
          )}
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
