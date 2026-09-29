import sourceCalls from "../../data/transcripts.json";
import type { CallFixture } from "./types";

type SourceCall = {
  id: string;
  title: string;
  metadata: {
    agent_id: string;
    member_id: string;
    call_date: string;
    duration_seconds: number;
  };
  crm_context: {
    member_name: string;
    plan_name: string;
    claim_id?: string;
    prior_authorization_id?: string;
    appeal_id?: string;
    known_providers?: string[];
  };
  transcript: string[];
  agent_notes?: string;
};

function duration(seconds: number) {
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

function toFixture(call: SourceCall): CallFixture {
  const providers = call.crm_context.known_providers ?? [];
  const rows = (
    [
      ["Agent ID", call.metadata.agent_id],
      ["Call date", call.metadata.call_date],
      ["Duration", duration(call.metadata.duration_seconds)],
      ["Member", call.crm_context.member_name],
      ["Plan", call.crm_context.plan_name],
      ["Provider", providers[0] ?? ""],
    ] as Array<[string, string]>
  ).filter(([, value]) => value);

  return {
    id: call.id,
    callId: call.id.replace(/^call_/, "CALL-").toUpperCase(),
    label: call.title,
    memberId: call.metadata.member_id,
    durationSeconds: call.metadata.duration_seconds,
    transcript: call.transcript.join("\n"),
    metadata: { agentId: call.metadata.agent_id, rows },
    agentNotes: call.agent_notes ?? "",
  };
}

export const SAMPLE_CALLS = (sourceCalls as SourceCall[]).map(toFixture);
export const DEFAULT_SAMPLE_ID = SAMPLE_CALLS[0].id;
