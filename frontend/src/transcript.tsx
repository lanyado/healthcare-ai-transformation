export type Speaker = "agent" | "caller";

export type Turn = {
  speaker: Speaker;
  text: string;
};

const TURN_PREFIX = /^(AGENT|CALLER):\s*(.*)$/i;

export function parseTranscript(transcript: string): Turn[] {
  const turns: Turn[] = [];
  for (const line of transcript.split("\n")) {
    const match = line.match(TURN_PREFIX);
    if (match) {
      turns.push({ speaker: match[1].toLowerCase() as Speaker, text: match[2] });
      continue;
    }
    if (!line.trim()) continue;
    if (turns.length) turns[turns.length - 1].text += `\n${line}`;
    else turns.push({ speaker: "caller", text: line });
  }
  return turns;
}

export function serializeTranscript(turns: Turn[]): string {
  return turns
    .map((turn) => `${turn.speaker === "agent" ? "AGENT" : "CALLER"}: ${turn.text}`)
    .join("\n");
}

function splitUtterance(text: string) {
  return {
    spoken: text.replace(/\s*\[[^\]]+\]/g, "").trim(),
    tones: [...text.matchAll(/\[([^\]]+)\]/g)].map((match) => match[1]),
  };
}

function joinUtterance(spoken: string, tones: string[]) {
  const suffix = tones.map((tone) => `[${tone}]`).join(" ");
  return suffix ? `${spoken} ${suffix}`.trim() : spoken;
}

function toneClass(tone: string) {
  return tone.toLowerCase().replace(/[^a-z]+/g, "-");
}

export function TranscriptChat({
  value,
  onChange,
  agentName,
}: {
  value: string;
  onChange: (value: string) => void;
  agentName?: string;
}) {
  const turns = parseTranscript(value);
  const commit = (next: Turn[]) => onChange(serializeTranscript(next));

  const editTurn = (index: number, spoken: string) => {
    const current = turns[index];
    const { tones } = splitUtterance(current.text);
    const text = joinUtterance(spoken, tones);
    if (!text) {
      commit(turns.filter((_, itemIndex) => itemIndex !== index));
      return;
    }
    commit(turns.map((turn, itemIndex) => (itemIndex === index ? { ...turn, text } : turn)));
  };

  return (
    <div className="transcript-chat" id="transcript">
      <div className="chat-thread" role="log" aria-label="Call Transcript">
        {turns.length === 0 && <p className="chat-empty">Start the conversation</p>}
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
              {start && turn.speaker === "caller" && <span className="chat-name">Caller</span>}
              {start && turn.speaker === "agent" && (
                <span className="chat-name">{agentName ? `${agentName}, Agent` : "Agent"}</span>
              )}
              <div className="chat-bubble">
                <span
                  aria-label={`${turn.speaker === "agent" ? "Agent" : "Caller"} message`}
                  contentEditable
                  role="textbox"
                  suppressContentEditableWarning
                  onBlur={(event) => editTurn(index, event.currentTarget.innerText)}
                >
                  {spoken}
                </span>
              </div>
              {tones.length > 0 && (
                <div className="chat-sentiments">
                  {tones.map((tone) => (
                    <span className={`chat-tone chat-tone--${toneClass(tone)}`} key={tone}>
                      {tone}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}
