export type AgentState = 'created' | 'planning' | 'running' | 'checking' | 'repairing' |
  'needs_input' | 'completed' | 'failed';

export type AgentCapability = 'DOCUMENT_QA' | 'ARTIFACT' | 'CALCULATION' | 'CODING' |
  'CODING_DEMO' | 'VISION';

export interface RouteDecision {
  capability: AgentCapability;
  model: string | null;
  reason: string;
}

export interface ToolEvent {
  state?: AgentState;
  reason?: string;
  tool?: string;
  status?: string;
  checks?: Record<string, boolean>;
}

export interface AgentResult {
  status: AgentState;
  task_id: string;
  user_intent: string;
  capability: AgentCapability;
  selected_model: string | null;
  route: RouteDecision;
  workflow: string;
  child_task_id: string | null;
  executed_steps: number;
  tool_results: ToolEvent[];
  artifacts: Record<string, string> | { name: string; url: string }[];
  checks: Record<string, boolean>;
  unresolved_issues: string[];
  timings: { total_seconds: number };
  resource: {
    max_steps: number;
    max_repairs: number;
    max_model_switches: number;
    max_context_tokens: number | null;
    output_budget_tokens: number | null;
    prompt_tokens: number | null;
    remaining_context_tokens: number | null;
    retrieved_evidence: number;
    tool_output_bytes: number;
    max_task_seconds: number;
  };
  result: {
    answer?: string;
    diff?: string;
    output_files?: { name: string; url: string }[];
    downloads?: { word: string; excel: string; slides: string };
    expression?: string;
    rounded?: number;
    steps?: string[];
    timings?: { switch_latency?: number; total_seconds?: number; [key: string]: number | undefined };
  };
}
