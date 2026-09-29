import { useEffect } from "react";
import { parseTranscript } from "./transcript";

function splitUtterance(text: string) {
  return {
    spoken: text.replace(/\s*\[[^\]]+\]/g, "").trim(),
    tones: [...text.matchAll(/\[([^\]]+)\]/g)].map((match) => match[1]),
  };
}

function toneClass(tone: string) {
  return tone.toLowerCase().replace(/[^a-z]+/g, "-");
}

type Props = {
  title: string;
  subtitle?: string;
  transcript: string;
  agentName?: string;
  onClose: () => void;
};

export function TranscriptViewer({ title, subtitle, transcript, agentName, onClose }: Props) {
  const turns = parseTranscript(transcript);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="transcript-overlay" onClick={onClose} role="presentation">
      <div
        className="transcript-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="transcript-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="transcript-title">{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Close transcript">
            <svg width="14" height="14" viewBox="0 0 256 256" fill="none" aria-hidden="true">
              <line x1="200" y1="56" x2="56" y2="200" stroke="currentColor" strokeWidth="16" strokeLinecap="round" />
              <line x1="200" y1="200" x2="56" y2="56" stroke="currentColor" strokeWidth="16" strokeLinecap="round" />
            </svg>
          </button>
        </header>
        <div className="transcript-modal-body">
          {turns.length === 0 ? <p className="chat-empty">No transcript for this call.</p> : null}
          {turns.map((turn, index) => {
            const previous = turns[index - 1];
            const next = turns[index + 1];
            const start = previous?.speaker !== turn.speaker;
            const end = next?.speaker !== turn.speaker;
            const { spoken, tones } = splitUtterance(turn.text);
            return (
              <div
                className={`chat-row chat-row--${turn.speaker}${start ? " chat-row--start" : ""}${end ? " chat-row--end" : ""}`}
                key={`${index}-${turn.speaker}`}
              >
                {start && turn.speaker === "caller" ? <span className="chat-name">Caller</span> : null}
                {start && turn.speaker === "agent" ? (
                  <span className="chat-name">{agentName ? `${agentName}, Agent` : "Agent"}</span>
                ) : null}
                <div className="chat-bubble">
                  <span>{spoken}</span>
                </div>
                {tones.length ? (
                  <div className="chat-sentiments">
                    {tones.map((tone) => (
                      <span className={`chat-tone chat-tone--${toneClass(tone)}`} key={tone}>
                        {tone}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
