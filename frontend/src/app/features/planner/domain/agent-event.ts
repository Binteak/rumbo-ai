import { Trip } from '../../trips/domain/trip';

/** Resumen de una ejecución completa del agente. */
export interface RunStats {
  iterations: number;
  toolCalls: number;
  toolErrors: number;
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
  status: string;
}

/** Fragmento de una guía recuperado por el RAG. */
export interface RagHit {
  source: string;
  destinationId: string;
  destination: string;
  section: string;
  text: string;
  score: number;
  match: { bm25Rank: number | null; vectorRank: number | null; vectorSimilarity: number | null };
}

export interface RagSearch {
  query: string;
  destinationId: string | null;
  retrieval: 'hybrid' | 'bm25';
  expandedTerms: string[];
  timingsMs: Record<string, number>;
  results: RagHit[];
}

/** Lo que el agente va contando mientras trabaja, en el orden en que ocurre. */
export type AgentEvent =
  | { type: 'run_started'; runId: string; sessionId: string; provider: string; model: string }
  | { type: 'thinking'; iteration: number }
  | { type: 'usage'; inputTokens: number; outputTokens: number }
  | { type: 'narration'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | {
      type: 'tool_result';
      id: string;
      name: string;
      /** Resultado tal y como lo devuelve la herramienta: se enseña en la traza sin transformar. */
      output: unknown;
      isError: boolean;
      durationMs: number;
      /** Solo en búsquedas en las guías que terminan bien. */
      rag?: RagSearch;
    }
  | { type: 'trip'; trip: Trip }
  | { type: 'notice'; text: string }
  | { type: 'final'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done'; stats: RunStats };
