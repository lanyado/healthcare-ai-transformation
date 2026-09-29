import { useEffect, useRef, useState, type ReactNode } from "react";
import { runExtraction, type CrmResult } from "./api";
import { DEFAULT_SAMPLE_ID, SAMPLE_CALLS } from "./calls";
import { CustomTranscript } from "./customTranscript";
import {
  callDuration,
  formatCallTime,
  formatIdentifiedAt,
  nextIdentification,
  segmentBounds,
  sliceTranscript,
  type Identification,
} from "./identifications";
import { PatientIdentity } from "./patientIdentity";
import { promptInjectionWarning } from "./promptGuard";
import { RecordingPlayer } from "./recordingPlayer";
import { TranscriptChat } from "./transcript";
import { TranscriptViewer } from "./transcriptViewer";
import type { CallFixture, Field, TopicResult } from "./types";

const HAS_RECORDING = new Set(["call_001", "call_002", "call_003", "call_004", "call_005"]);

const CUSTOM_ID = "custom";
const CUSTOM_CALL_ID = "call_custom";

function Rows({ items }: { items: Array<[string, ReactNode]> }) {
  return items.map(([label, value]) => (
    <div key={label}>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  ));
}

function FieldRows({ fields }: { fields: Field[] }) {
  return (
    <dl className="field-rows">
      {fields.map(({ label, value }) => (
        <div className="field-row" key={label}>
          <dt>{label}</dt>
          <dd>
            {value === "Yes" || value === "No" ? (
              <span className={`value-pill value-pill--${value.toLowerCase()}`}>{value}</span>
            ) : (
              value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ListRow({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="list-row">
      <h4>{label}</h4>
      {items.length > 1 ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{items[0] ?? "None"}</p>
      )}
    </div>
  );
}

function Banner({ title, body, kind }: { title: string; body: string; kind?: "loading" | "error" }) {
  return (
    <div className={kind ? `state-message state-message--${kind}` : "state-message"} role={kind === "error" ? "alert" : "status"}>
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

export function App() {
  const [sampleId, setSampleId] = useState(DEFAULT_SAMPLE_ID);
  const [fixture, setFixture] = useState<CallFixture | null>(null);
  const [transcript, setTranscript] = useState("");
  const [crm, setCrm] = useState<CrmResult | null>(null);
  const [activeTopic, setActiveTopic] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "error">("ready");
  const [loadError, setLoadError] = useState("");
  const [patientId, setPatientId] = useState("");
  const [identifications, setIdentifications] = useState<Identification[]>([]);
  const [activeIdentId, setActiveIdentId] = useState("");
  const [identityMode, setIdentityMode] = useState<"view" | "correct" | "new">("view");
  const [patientDraft, setPatientDraft] = useState("");
  const [demoOpen, setDemoOpen] = useState(true);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [markSeconds, setMarkSeconds] = useState(0);
  const playbackRef = useRef(0);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const [legIndex, setLegIndex] = useState(0);

  const isCustom = sampleId === CUSTOM_ID;

  useEffect(() => {
    if (sampleId === CUSTOM_ID) {
      setFixture(null);
      setTranscript("");
      setPatientId("");
      setIdentifications([]);
      setActiveIdentId("");
      setIdentityMode("view");
      setPatientDraft("");
      playbackRef.current = 0;
      setMarkSeconds(0);
      setRecordingDuration(0);
      setCrm(null);
      setLegIndex(0);
      setActiveTopic("");
      setLoadError("");
      setStatus("ready");
      setPlayerOpen(false);
      setTranscriptOpen(false);
      return;
    }

    const data = SAMPLE_CALLS.find((item) => item.id === sampleId);
    if (!data) return;
    setFixture(data);
    setTranscript(data.transcript);
    const first = nextIdentification(data.memberId, 0);
    setPatientId(data.memberId);
    setIdentifications([first]);
    setActiveIdentId(first.id);
    setIdentityMode("view");
    setPatientDraft(data.memberId);
    playbackRef.current = 0;
    setMarkSeconds(0);
    setRecordingDuration(0);
    setCrm(null);
    setLegIndex(0);
    setActiveTopic("");
    setLoadError("");
    setStatus("ready");
    setPlayerOpen(false);
    setTranscriptOpen(false);
  }, [sampleId]);

  const activeResult: TopicResult | null = !crm
    ? null
    : crm.topics.find((topic) => topic.id === activeTopic) ?? crm.topics[0] ?? null;
  const legs = crm?.legs?.length ? crm.legs : [];
  const activeLeg = legs[legIndex] ?? null;
  const recordingId = activeLeg?.id ?? fixture?.id ?? "";
  const canPlay = HAS_RECORDING.has(recordingId);
  const activeIdent = identifications.find((item) => item.id === activeIdentId) ?? null;
  const combinedTranscript = legs.length > 1
    ? legs.map((leg) => leg.transcript).filter(Boolean).join("\n")
    : transcript;
  const durationSeconds = callDuration(combinedTranscript, recordingDuration || fixture?.durationSeconds);
  const bounds = segmentBounds(identifications, activeIdentId);
  const patientTranscript = activeIdent
    ? sliceTranscript(combinedTranscript, durationSeconds, bounds.start, bounds.end)
    : combinedTranscript;
  const identified = Boolean(activeIdent?.patientId.trim());

  const submitIdentity = () => {
    const value = patientDraft.trim();
    if (!value) return;
    const mark = playbackRef.current;
    if (identityMode === "correct" && activeIdent) {
      const updated = { ...activeIdent, patientId: value, identifiedAt: Date.now() };
      setIdentifications((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      setPatientId(value);
    } else {
      const created = nextIdentification(value, mark);
      setIdentifications((items) => [...items, created].sort((left, right) => left.offsetSeconds - right.offsetSeconds));
      setActiveIdentId(created.id);
      setPatientId(value);
    }
    setIdentityMode("view");
  };

  const handleRun = () => {
    const customText = transcript.trim();
    const injection = isCustom ? promptInjectionWarning(customText) : null;
    if (!identified) {
      setLoadError("Identify a member ID first.");
      setStatus("error");
      return;
    }
    if (isCustom && (!customText || injection)) {
      setLoadError(injection || "Add a .txt file or type a transcript first.");
      setStatus("error");
      return;
    }
    if (!isCustom && !fixture) return;

    setStatus("loading");
    setLoadError("");
    setCrm(null);
    const job = isCustom
      ? runExtraction(CUSTOM_CALL_ID, { transcript: customText, memberId: activeIdent!.patientId.trim() })
      : runExtraction(fixture!.id);
    void job
      .then((result) => {
        setCrm(result);
        setActiveTopic(result.topics[0]?.id ?? "");
        setLegIndex(Math.max((result.legs?.length ?? 1) - 1, 0));
        setStatus("ready");
      })
      .catch((error) => {
        setLoadError(error instanceof Error ? error.message : "Extraction failed.");
        setStatus("error");
      });
  };

  return (
    <main className={demoOpen ? "workspace" : "workspace workspace--demo-collapsed"}>
      <section className={demoOpen ? "demo-pane" : "demo-pane is-collapsed"} aria-labelledby="demo-title">
        <header className="pane-header pane-header--demo">
          <button
            className="demo-toggle"
            type="button"
            aria-expanded={demoOpen}
            aria-controls="demo-content"
            onClick={() => setDemoOpen((open) => !open)}
          >
            <span className="demo-toggle-copy">
              <h1 id="demo-title">Extraction Demo (Internal testing tool)</h1>
            </span>
            <span className="demo-toggle-icon" aria-hidden="true">
              {demoOpen ? "‹" : "›"}
            </span>
          </button>
        </header>

        <div className="demo-content" id="demo-content" hidden={!demoOpen}>
          <label className="control-group">
            <span>Sample Call</span>
            <select value={sampleId} onChange={(event) => setSampleId(event.target.value)}>
              {SAMPLE_CALLS.map((item) => (
                <option key={item.id} value={item.id}>{item.label}</option>
              ))}
              <option value={CUSTOM_ID}>Custom</option>
            </select>
          </label>

          <div className="control-group transcript-control">
            <span>Call Transcript</span>
            {isCustom ? (
              <CustomTranscript value={transcript} onChange={setTranscript} />
            ) : (
              <TranscriptChat
                key={sampleId}
                value={transcript}
                onChange={setTranscript}
                agentName={fixture?.metadata.agentId}
              />
            )}
          </div>

          <div className="demo-actions">
            <button className="primary-button" type="button" onClick={handleRun} disabled={status === "loading" || !identified || (isCustom && !transcript.trim())}>
              {status === "loading" ? "Processing call…" : "Run Extraction"}
            </button>
            <button
              className="reset-button"
              type="button"
              onClick={() => {
                setTranscript(fixture?.transcript ?? "");
                if (fixture) {
                  const first = nextIdentification(fixture.memberId, 0);
                  setPatientId(fixture.memberId);
                  setIdentifications([first]);
                  setActiveIdentId(first.id);
                  setPatientDraft(fixture.memberId);
                } else {
                  setPatientId("");
                  setIdentifications([]);
                  setActiveIdentId("");
                  setPatientDraft("");
                }
                setIdentityMode("view");
                playbackRef.current = 0;
                setMarkSeconds(0);
                setCrm(null);
                setLegIndex(0);
                setActiveTopic("");
                setLoadError("");
                setStatus("ready");
                setPlayerOpen(false);
                setTranscriptOpen(false);
              }}
            >
              Reset
            </button>
          </div>
        </div>
      </section>

      <section className="crm-pane" aria-labelledby="crm-title">
        <header className="pane-header pane-header--crm">
          <div>
            <h1 id="crm-title">{activeLeg?.callId ?? crm?.callId ?? fixture?.callId ?? "New call"}</h1>
            <p>{legs.length > 1 ? `Agent CRM · connected call ${legIndex + 1} of ${legs.length}` : "Agent CRM"}</p>
          </div>
          <PatientIdentity
            identifications={identifications}
            activeId={activeIdentId}
            draft={patientDraft}
            mode={identityMode}
            markSeconds={markSeconds}
            onDraft={setPatientDraft}
            onSelect={(id) => {
              const selected = identifications.find((item) => item.id === id);
              if (!selected) return;
              setActiveIdentId(id);
              setPatientId(selected.patientId);
              setPatientDraft(selected.patientId);
              setIdentityMode("view");
            }}
            onStartCorrect={() => {
              setPatientDraft(activeIdent?.patientId ?? "");
              setIdentityMode("correct");
            }}
            onStartNew={() => {
              setPatientDraft("");
              setMarkSeconds(playbackRef.current);
              setIdentityMode("new");
            }}
            onCancel={() => {
              setPatientDraft(activeIdent?.patientId ?? "");
              setIdentityMode("view");
            }}
            onSubmit={submitIdentity}
          />
        </header>

        <div className="crm-content">
          {(fixture || crm) && (
            <>
              <section className="metadata-section" aria-labelledby="metadata-title">
                <div className="metadata-head">
                  <h2 id="metadata-title">Call Metadata</h2>
                  {legs.length > 1 ? (
                    <div className="call-pager">
                      <button type="button" disabled={legIndex <= 0} onClick={() => setLegIndex((index) => index - 1)}>
                        Back
                      </button>
                      <p>
                        {activeLeg?.callId} · {legIndex + 1} of {legs.length}
                      </p>
                      <button
                        type="button"
                        disabled={legIndex >= legs.length - 1}
                        onClick={() => setLegIndex((index) => index + 1)}
                      >
                        Next
                      </button>
                    </div>
                  ) : null}
                </div>
                <dl className="metadata-grid">
                  <Rows
                    items={[
                      ...(activeLeg?.metadata.rows ?? crm?.metadata.rows ?? fixture?.metadata.rows ?? []),
                      ...(activeIdent
                        ? [
                            ["Identified", formatIdentifiedAt(activeIdent.identifiedAt)] as [string, string],
                            ["Transcript from", formatCallTime(activeIdent.offsetSeconds)] as [string, string],
                          ]
                        : []),
                      [
                        "Recording",
                        canPlay ? (
                          <a
                            href={`#recording-${recordingId}`}
                            onClick={(event) => {
                              event.preventDefault();
                              setTranscriptOpen(false);
                              setPlayerOpen(true);
                            }}
                          >
                            View recording
                          </a>
                        ) : (
                          "None"
                        ),
                      ],
                      [
                        "Transcript",
                        transcript.trim() ? (
                          <a
                            href="#transcript"
                            onClick={(event) => {
                              event.preventDefault();
                              setPlayerOpen(false);
                              setTranscriptOpen(true);
                            }}
                          >
                            View transcript
                          </a>
                        ) : (
                          "None"
                        ),
                      ],
                    ]}
                  />
                </dl>
              </section>
              {fixture ? (
                <label className="notes-control">
                  <span>Agent Notes</span>
                  <textarea key={fixture.id} defaultValue={fixture.agentNotes} />
                </label>
              ) : null}
            </>
          )}

          {status === "loading" && (
            <Banner kind="loading" title="Processing call…" body="Normalizing → Detecting topics → Extracting → Validating" />
          )}
          {status === "error" && <Banner kind="error" title="Extraction failed" body={loadError || "Please try again."} />}
          {status === "ready" && isCustom && !crm && (
            <Banner title="Custom transcript" body="Drop a .txt file or type a transcript, then run extraction." />
          )}
          {status === "ready" && fixture && !crm && (
            <Banner title="No extraction result yet" body="Run extraction to queue this call and fill the AI insights from the CRM." />
          )}

          {status === "ready" && crm && activeResult && (
            <section className="ai-insights" aria-label="AI insights">
              <div className="topic-tabs-block">
                <div className="ai-insights-head">
                  <h2 id="topics-title">Topics Discussed</h2>
                  <p className="ai-insights-badge">AI generated</p>
                </div>
                <nav className="topic-tabs" aria-labelledby="topics-title">
                  {crm.topics.map((topic) => (
                    <button
                      className={activeTopic === topic.id ? "is-active" : ""}
                      key={topic.id}
                      type="button"
                      onClick={() => setActiveTopic(topic.id)}
                    >
                      {topic.label}
                    </button>
                  ))}
                </nav>
                {activeResult.summary ? (
                  <section className="summary-row" aria-labelledby="summary-title">
                    <h2 id="summary-title">AI Summary</h2>
                    <p>{activeResult.summary}</p>
                  </section>
                ) : null}
              </div>

              <div className="ai-output">
                <section className="details-column" aria-labelledby="details-title">
                  <div className="section-heading">
                    <h2 id="details-title">Call Details</h2>
                    <p>Generated from transcript</p>
                  </div>
                  <FieldRows fields={activeResult.fields} />
                  {(activeResult.agentActions.length ||
                    activeResult.agentCommitments.length ||
                    activeResult.callerCommitments.length) ? (
                    <div className="lists-group">
                      {activeResult.agentActions.length ? (
                        <ListRow label="Agent Actions" items={activeResult.agentActions} />
                      ) : null}
                      {activeResult.agentCommitments.length ? (
                        <ListRow label="Agent Commitments" items={activeResult.agentCommitments} />
                      ) : null}
                      {activeResult.callerCommitments.length ? (
                        <ListRow label="Caller Commitments" items={activeResult.callerCommitments} />
                      ) : null}
                    </div>
                  ) : null}
                </section>
              </div>
            </section>
          )}
        </div>
      </section>
      {playerOpen && canPlay ? (
        <RecordingPlayer
          src={`/api/recordings/${recordingId}`}
          title={crm?.callId ?? fixture?.callId ?? "Call recording"}
          subtitle={activeLeg?.label ?? fixture?.label}
          onTime={(seconds) => {
            playbackRef.current = seconds;
            if (identityMode !== "view") setMarkSeconds(seconds);
          }}
          onDuration={setRecordingDuration}
          onClose={() => setPlayerOpen(false)}
        />
      ) : null}
      {transcriptOpen && patientTranscript.trim() ? (
        <TranscriptViewer
          title={activeIdent?.patientId ?? crm?.callId ?? fixture?.callId ?? "Call transcript"}
          subtitle={
            legs.length > 1
              ? `${crm?.callId ?? "Call"} · ${legs.length} connected calls`
              : activeIdent
                ? `${fixture?.label ?? "Call"} · from ${formatCallTime(activeIdent.offsetSeconds)}`
                : fixture?.label ?? "Call transcript"
          }
          transcript={patientTranscript}
          agentName={fixture?.metadata.agentId}
          onClose={() => setTranscriptOpen(false)}
        />
      ) : null}
    </main>
  );
}
