import { GlobalStats, Health, Usage } from '../domain/system-status';

/** Formas exactas de las respuestas del backend (snake_case). Solo se usan en esta capa. */

export interface HealthDto {
  status: string;
  mode: string;
  model: string;
}

export interface UsageDto {
  mode: string;
  model: string;
  real_ai: boolean;
  chain?: string[];
  remaining?: { hour: number; day: number };
  budget_remaining_pct?: number;
}

export interface GlobalStatsDto {
  runs: number;
  success_rate: number | null;
  avg_duration_ms: number;
  avg_iterations: number;
  tool_calls: number;
  tool_errors: number;
  tokens: number;
  trips: number;
}

export function toHealth(dto: HealthDto): Health {
  return { status: dto.status, provider: dto.mode, model: dto.model };
}

export function toUsage(dto: UsageDto): Usage {
  return {
    provider: dto.mode,
    model: dto.model,
    realAi: dto.real_ai,
    chain: dto.chain,
    remaining: dto.remaining,
    budgetRemainingPct: dto.budget_remaining_pct,
  };
}

export function toGlobalStats(dto: GlobalStatsDto): GlobalStats {
  return {
    runs: dto.runs,
    successRate: dto.success_rate,
    avgDurationMs: dto.avg_duration_ms,
    avgIterations: dto.avg_iterations,
    toolCalls: dto.tool_calls,
    toolErrors: dto.tool_errors,
    tokens: dto.tokens,
    trips: dto.trips,
  };
}
