import { TripDto, toTrip } from '../../trips/infrastructure/trip.dto';
import { AgentEvent, RagSearch } from '../domain/agent-event';

/** Eventos tal y como llegan por el stream del backend (snake_case). Solo se usan en esta capa. */

export interface RunStatsDto {
  iterations: number;
  tool_calls: number;
  tool_errors: number;
  input_tokens: number;
  output_tokens: number;
  duration_ms: number;
  status: string;
}

export interface RagHitDto {
  source: string;
  destination_id: string;
  destination: string;
  section: string;
  text: string;
  score: number;
  match: { bm25_rank: number | null; vector_rank: number | null; vector_similarity: number | null };
}

export interface RagSearchDto {
  query: string;
  destination_id: string | null;
  retrieval: 'hybrid' | 'bm25';
  expanded_terms: string[];
  timings_ms: Record<string, number>;
  results: RagHitDto[];
}

export type AgentEventDto =
  | { type: 'run_started'; run_id: string; session_id: string; mode: string; model: string }
  | { type: 'thinking'; iteration: number }
  | { type: 'usage'; input_tokens: number; output_tokens: number }
  | { type: 'narration'; text: string }
  | { type: 'tool_call'; id: string; name: string; input: Record<string, unknown> }
  | {
      type: 'tool_result';
      id: string;
      name: string;
      output: unknown;
      is_error: boolean;
      duration_ms: number;
    }
  | { type: 'trip'; trip: TripDto }
  | { type: 'notice'; text: string }
  | { type: 'final'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done'; stats: RunStatsDto };

/** Herramienta cuyo resultado son las fuentes del RAG. */
const GUIDES_TOOL = 'search_travel_guides';

export function toRagSearch(dto: RagSearchDto): RagSearch {
  return {
    query: dto.query,
    destinationId: dto.destination_id,
    retrieval: dto.retrieval,
    expandedTerms: dto.expanded_terms,
    timingsMs: dto.timings_ms,
    results: dto.results.map((hit) => ({
      source: hit.source,
      destinationId: hit.destination_id,
      destination: hit.destination,
      section: hit.section,
      text: hit.text,
      score: hit.score,
      match: {
        bm25Rank: hit.match.bm25_rank,
        vectorRank: hit.match.vector_rank,
        vectorSimilarity: hit.match.vector_similarity,
      },
    })),
  };
}

/**
 * Traduce un evento del stream al dominio. Devuelve `null` si el tipo no se conoce: así un
 * evento nuevo del backend no rompe la interfaz mientras no se le dé soporte.
 */
export function toAgentEvent(dto: AgentEventDto): AgentEvent | null {
  switch (dto.type) {
    case 'run_started':
      return {
        type: 'run_started',
        runId: dto.run_id,
        sessionId: dto.session_id,
        provider: dto.mode,
        model: dto.model,
      };
    case 'usage':
      return { type: 'usage', inputTokens: dto.input_tokens, outputTokens: dto.output_tokens };
    case 'tool_result':
      return {
        type: 'tool_result',
        id: dto.id,
        name: dto.name,
        output: dto.output,
        isError: dto.is_error,
        durationMs: dto.duration_ms,
        rag:
          dto.name === GUIDES_TOOL && !dto.is_error
            ? toRagSearch(dto.output as RagSearchDto)
            : undefined,
      };
    case 'trip':
      return { type: 'trip', trip: toTrip(dto.trip) };
    case 'done':
      return {
        type: 'done',
        stats: {
          iterations: dto.stats.iterations,
          toolCalls: dto.stats.tool_calls,
          toolErrors: dto.stats.tool_errors,
          inputTokens: dto.stats.input_tokens,
          outputTokens: dto.stats.output_tokens,
          durationMs: dto.stats.duration_ms,
          status: dto.stats.status,
        },
      };
    case 'thinking':
    case 'narration':
    case 'tool_call':
    case 'notice':
    case 'final':
    case 'error':
      return dto;
    default:
      return null;
  }
}
