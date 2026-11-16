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

/** En qué situación está un modelo de la cadena. */
export type ProviderState = 'active' | 'standby' | 'paused';

/** Un modelo de la cadena (Gemini → Groq → DeepSeek → demo) y la cuota que le queda hoy. */
export interface ProviderStatus {
  name: string;
  label: string;
  model: string;
  /** "active": responde ahora; "standby": de respaldo; "paused": sin cuota o caído, en pausa. */
  status: ProviderState;
  pausedSeconds?: number;
  callsToday?: number;
  /** Llamadas al día de su plan gratuito (orientativo); null si no se conoce. */
  dailyLimit?: number | null;
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
  /** Toda la cadena de modelos, con el demo al final. */
  providers?: ProviderStatus[];
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

const MODEL_WORDS: Record<string, string> = {
  gpt: 'GPT',
  oss: 'OSS',
  deepseek: 'DeepSeek',
  gemini: 'Gemini',
  claude: 'Claude',
  llama: 'Llama',
  qwen: 'Qwen',
  latest: '(última)',
};

/**
 * Nombre de producto de un modelo: "gemini-3.5-flash-lite" → "Gemini 3.5 Flash-Lite",
 * "openai/gpt-oss-120b" → "GPT-OSS 120B", "claude-sonnet-5-5" → "Claude Sonnet 5.5".
 */
export function prettyModelName(model: string): string {
  const id = (model.split('/').pop() ?? '').replace(/:free$/, '');
  if (!id || id === 'rumbo-demo') return 'Modo demo';
  const parts: string[] = [];
  for (const raw of id
    .replace(/gpt-oss/i, 'gpt_oss')
    .replace(/flash-lite/i, 'flash_lite')
    .split('-')) {
    const last = parts[parts.length - 1];
    if (/^\d+$/.test(raw) && last && /^\d+(\.\d+)*$/.test(last)) {
      parts[parts.length - 1] = `${last}.${raw}`; // "5-5" → "5.5"
      continue;
    }
    parts.push(
      raw
        .split('_')
        .map(
          (w) =>
            MODEL_WORDS[w.toLowerCase()] ??
            (/^(\d+[a-z]|v\d+)$/i.test(w) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)),
        )
        .join('-'),
    );
  }
  return parts.join(' ');
}

/**
 * La cadena tal y como se le muestra al usuario. Si ha elegido el modo demo (o está en el móvil),
 * el demo es quien responde y los modelos reales quedan de respaldo.
 */
export function chainForDisplay(usage: Usage | null, mode: ChatMode): ProviderStatus[] {
  const chain = usage?.providers ?? [];
  if (mode !== 'demo') return chain;
  return chain.map((p) => ({
    ...p,
    status: p.name === DEMO_PROVIDER ? 'active' : p.status === 'active' ? 'standby' : p.status,
  }));
}

/** "≈ 477 de 500 llamadas hoy", "En pausa · vuelve en 12 min", "Sin límite · respuestas con reglas". */
export function quotaText(p: ProviderStatus): string {
  if (p.name === DEMO_PROVIDER) return 'Sin límite · respuestas con reglas';
  if (p.status === 'paused') return `En pausa · vuelve en ${formatWait(p.pausedSeconds ?? 0)}`;
  const used = p.callsToday ?? 0;
  if (p.dailyLimit) return `≈ ${Math.max(0, p.dailyLimit - used)} de ${p.dailyLimit} llamadas hoy`;
  return `${used} ${used === 1 ? 'llamada' : 'llamadas'} hoy`;
}

/** 45 → "1 min", 3600 → "1 h", 5400 → "1 h 30 min". */
export function formatWait(seconds: number): string {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}
