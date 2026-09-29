import { parseTranscript, serializeTranscript } from "./transcript";

export type Identification = {
  id: string;
  patientId: string;
  identifiedAt: number;
  offsetSeconds: number;
};

export function formatCallTime(seconds: number) {
  const safe = Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
  const minutes = Math.floor(safe / 60);
  const rest = Math.floor(safe % 60);
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function formatIdentifiedAt(ms: number) {
  return new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function callDuration(transcript: string, known?: number) {
  if (known && known > 0) return known;
  const chars = parseTranscript(transcript).reduce((total, turn) => total + turn.text.length, 0);
  return Math.max(chars / 12, 1);
}

export function sliceTranscript(
  transcript: string,
  durationSeconds: number,
  startSeconds: number,
  endSeconds = Number.POSITIVE_INFINITY,
) {
  const turns = parseTranscript(transcript);
  if (!turns.length) return "";
  const weights = turns.map((turn) => Math.max(turn.text.length, 1));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  let elapsed = 0;
  const kept = turns.filter((_, index) => {
    const at = (elapsed / total) * durationSeconds;
    elapsed += weights[index];
    return at >= startSeconds && at < endSeconds;
  });
  return serializeTranscript(kept);
}

export function segmentBounds(identifications: Identification[], activeId: string) {
  const ordered = [...identifications].sort((left, right) => left.offsetSeconds - right.offsetSeconds);
  const index = ordered.findIndex((item) => item.id === activeId);
  const current = index >= 0 ? ordered[index] : null;
  const next = index >= 0 ? ordered[index + 1] : null;
  return {
    start: current?.offsetSeconds ?? 0,
    end: next?.offsetSeconds ?? Number.POSITIVE_INFINITY,
  };
}

export function nextIdentification(
  patientId: string,
  offsetSeconds: number,
  at = Date.now(),
): Identification {
  return {
    id: `id-${at}`,
    patientId,
    identifiedAt: at,
    offsetSeconds: Math.max(offsetSeconds, 0),
  };
}
