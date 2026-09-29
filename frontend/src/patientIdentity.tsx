import {
  formatCallTime,
  formatIdentifiedAt,
  type Identification,
} from "./identifications";

type Props = {
  identifications: Identification[];
  activeId: string;
  draft: string;
  mode: "view" | "correct" | "new";
  markSeconds: number;
  onDraft: (value: string) => void;
  onSelect: (id: string) => void;
  onStartCorrect: () => void;
  onStartNew: () => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function PatientIdentity({
  identifications,
  activeId,
  draft,
  mode,
  markSeconds,
  onDraft,
  onSelect,
  onStartCorrect,
  onStartNew,
  onCancel,
  onSubmit,
}: Props) {
  const active = identifications.find((item) => item.id === activeId) ?? null;
  const showInput = mode !== "view" || !active;

  const submit = () => {
    if (!draft.trim()) return;
    onSubmit();
  };

  return (
    <div className="patient-identity">
      {identifications.length > 0 ? (
        <nav className="patient-screens" aria-label="Members on this call">
          {identifications.map((item) => (
            <button
              className={item.id === activeId ? "is-active" : ""}
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
            >
              {item.patientId}
            </button>
          ))}
        </nav>
      ) : null}

      <label className="patient-id-control">
        <span>Member ID</span>
        {showInput ? (
          <input
            aria-label="Member ID"
            autoComplete="off"
            spellCheck={false}
            value={draft}
            placeholder="Enter member ID"
            onChange={(event) => onDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submit();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                onCancel();
              }
            }}
          />
        ) : (
          <a
            className="patient-id-link"
            href={`#patient-${active?.patientId}`}
            onClick={(event) => {
              event.preventDefault();
              onStartCorrect();
            }}
          >
            {active?.patientId}
          </a>
        )}
        <span className="patient-id-meta">
          {mode === "new"
            ? `New screen from ${formatCallTime(markSeconds)}`
            : mode === "correct"
              ? `Correction resets identification time · transcript stays from ${formatCallTime(active?.offsetSeconds ?? 0)}`
              : active
                ? `Identified ${formatIdentifiedAt(active.identifiedAt)} · from ${formatCallTime(active.offsetSeconds)}`
                : "Submit to identify and open a member screen"}
        </span>
      </label>

      <div className="patient-id-actions">
        {showInput ? (
          <>
            <button className="patient-id-submit" type="button" onClick={submit} disabled={!draft.trim()}>
              Identify
            </button>
            {mode !== "view" ? (
              <button className="patient-id-cancel" type="button" onClick={onCancel}>
                Cancel
              </button>
            ) : null}
          </>
        ) : (
          <button className="patient-id-new" type="button" onClick={onStartNew}>
            New member
          </button>
        )}
      </div>
    </div>
  );
}
