import type { CallMetadata, TopicResult } from "./types";

export type CallLeg = {
  id: string;
  callId: string;
  label: string;
  metadata: CallMetadata;
  transcript: string;
};

export type CrmResult = {
  id: string;
  callId: string;
  label: string;
  patientId: string;
  metadata: CallMetadata;
  topics: TopicResult[];
  legs?: CallLeg[];
};

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  const body = (await response.json().catch(() => ({}))) as T & { detail?: string };
  if (!response.ok) throw new Error(body.detail || fallback);
  return body;
}

export async function runExtraction(
  callId: string,
  custom?: { transcript: string; memberId: string },
): Promise<CrmResult> {
  const started = await fetch("/api/extractions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      call_id: callId,
      ...(custom ? { transcript: custom.transcript, member_id: custom.memberId } : {}),
    }),
  });
  await readJson(started, "Could not queue extraction.");

  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const response = await fetch(`/api/extractions/${encodeURIComponent(callId)}`);
    const current = await readJson<{ status: string; error?: string; crm?: CrmResult }>(
      response,
      "Could not load extraction status.",
    );
    if (current.status === "ready" && current.crm) return current.crm;
    if (current.status === "error") throw new Error(current.error || "Extraction failed.");
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
  }
  throw new Error("Extraction timed out.");
}

export async function checkCustomTranscript(transcript: string): Promise<string | null> {
  const response = await fetch("/api/transcripts/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript }),
  });
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  if (!response.ok) return body.detail || "This transcript could not be used.";
  return null;
}
