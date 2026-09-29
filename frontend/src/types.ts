export type CallMetadata = {
  agentId: string;
  rows: Array<[string, string]>;
};

export type Field = {
  label: string;
  value: string;
};

export type TopicResult = {
  id: string;
  label: string;
  fields: Field[];
  agentActions: string[];
  agentCommitments: string[];
  callerCommitments: string[];
  summary: string;
};

export type CallFixture = {
  id: string;
  callId: string;
  label: string;
  memberId: string;
  durationSeconds: number;
  transcript: string;
  metadata: CallMetadata;
  agentNotes: string;
};
