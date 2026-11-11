/** Estado del servicio: qué modelo responde, cuánto cupo queda y con qué modo se enviará el mensaje. */

/** Quién responde: el modelo real configurado o el modo demo (reglas, sin coste). */
export type ChatMode = 'real' | 'demo';

/** Nombre con el que el backend identifica el modo demo. */
export const DEMO_PROVIDER = 'demo';

export interface Health {
  status: string;
  /** Proveedor principal de la instancia: "claude", "gemini", "groq"... o "demo". */
  provider: string;
  model: string;
}

/** Con qué se atenderá a este usuario y cuántas consultas con IA real le quedan. */
export interface Usage {
  provider: string;
  model: string;
  realAi: boolean;
  /** Proveedores reales configurados, en orden de prioridad. */
  chain?: string[];
  remaining?: { hour: number; day: number };
  budgetRemainingPct?: number;
}

export interface GlobalStats {
  runs: number;
  successRate: number | null;
  avgDurationMs: number;
  avgIterations: number;
  toolCalls: number;
  toolErrors: number;
  tokens: number;
  trips: number;
}

/** El uso es más preciso que la salud (tiene en cuenta cuotas y pausas), así que manda. */
export function currentProvider(usage: Usage | null, health: Health | null): string {
  return usage?.provider ?? health?.provider ?? '';
}

/** True si el backend tiene algún modelo real configurado. */
export function isRealAvailable(usage: Usage | null, health: Health | null): boolean {
  const provider = currentProvider(usage, health);
  return !!provider && provider !== DEMO_PROVIDER;
}

/** Modo con el que se enviará el próximo mensaje. Con `demoOnly` (versión móvil) siempre es demo. */
export function resolveMode(
  realAvailable: boolean,
  preferred: ChatMode,
  demoOnly = false,
): ChatMode {
  return !demoOnly && realAvailable && preferred === 'real' ? 'real' : 'demo';
}

/** True si la próxima respuesta será del modo demo: por elección, sin modelo o con el cupo agotado. */
export function answersInDemo(mode: ChatMode, usage: Usage | null, health: Health | null): boolean {
  if (mode === 'demo') return true;
  return usage ? !usage.realAi : health?.provider === DEMO_PROVIDER;
}

/** "openai/gpt-oss-120b" → "gpt-oss-120b". */
export function shortModelName(usage: Usage | null, health: Health | null): string {
  return (usage?.model ?? health?.model ?? '').split('/').pop() ?? '';
}
