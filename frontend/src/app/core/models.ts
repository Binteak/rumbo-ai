export interface Activity {
  slot: string;
  name: string;
  category: string;
  duration_h: number;
  price_eur: number;
  area: string;
}

export interface TripDay {
  day: number;
  activities: Activity[];
}

export interface Budget {
  per_person: Record<string, number>;
  total_per_person_eur: number;
  total_eur: number;
  style: string;
  days: number;
  travelers: number;
}

export interface Climate {
  month: string;
  avg_temp_c: number;
  rain_days: number;
  verdict: string;
}

export interface Trip {
  id: number;
  created_at: string;
  title: string;
  destination_id: string;
  destination_name: string;
  flag: string;
  month: number | null;
  days: number;
  travelers: number;
  style: string;
  summary: string;
  climate: Climate | null;
  budget: Budget;
  itinerary: TripDay[];
}

export interface RunStats {
  iterations: number;
  tool_calls: number;
  tool_errors: number;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
  status: string;
}

export type AgentEvent =
  | { type: 'run_started'; run_id: string; session_id: string; mode: string; model: string }
  | { type: 'thinking'; iteration: number }
  | { type: 'usage'; input_tokens: number; output_tokens: number }
  | { type: 'narration'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | { type: 'tool_result'; id: string; name: string; output: unknown; is_error: boolean; duration_ms: number }
  | { type: 'trip'; trip: Trip }
  | { type: 'notice'; text: string }
  | { type: 'final'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done'; stats: RunStats };

/** Quién responde: el modelo real configurado (Gemini, Groq, Claude) o el modo demo. */
export type ChatMode = 'real' | 'demo';

export interface Health {
  status: string;
  mode: string;
  model: string;
}

/** Modo con el que se atenderá al usuario y cuántas consultas con IA real le quedan. */
export interface Usage {
  mode: string;
  model: string;
  real_ai: boolean;
  /** Proveedores reales configurados, en orden de prioridad. */
  chain?: string[];
  remaining?: { hour: number; day: number };
  budget_remaining_pct?: number;
}

export interface GlobalStats {
  runs: number;
  success_rate: number | null;
  avg_duration_ms: number;
  avg_iterations: number;
  tool_calls: number;
  tool_errors: number;
  tokens: number;
  trips: number;
}

export interface ChatMessage {
  role: 'user' | 'agent' | 'notice';
  text: string;
}

/** Fragmento recuperado por el RAG (salida de search_travel_guides). */
export interface RagHit {
  source: string;
  destination_id: string;
  destination: string;
  section: string;
  text: string;
  score: number;
  match: { bm25_rank: number | null; vector_rank: number | null; vector_similarity: number | null };
}

export interface RagSearch {
  query: string;
  destination_id: string | null;
  retrieval: 'hybrid' | 'bm25';
  expanded_terms: string[];
  timings_ms: Record<string, number>;
  results: RagHit[];
}

/** Paso visible en la traza del agente. */
export interface TraceStep {
  id: string;
  kind: 'thinking' | 'narration' | 'tool' | 'notice' | 'final' | 'error';
  title: string;
  detail?: string;
  input?: Record<string, unknown>;
  output?: unknown;
  status: 'running' | 'ok' | 'error';
  duration_ms?: number;
  /** Solo en search_travel_guides: fuentes recuperadas por el RAG. */
  rag?: RagSearch;
}
