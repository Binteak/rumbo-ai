import { AgentEvent, RagSearch, RunStats } from './agent-event';

/** Por qué ha fallado un turno: lo dice el agente o no se ha podido hablar con el servidor. */
export type FailureCause = 'agent' | 'connection';

export type ChatMessage =
  | { role: 'user' | 'agent' | 'notice'; text: string }
  | { role: 'failure'; cause: FailureCause; text: string };

export type StepStatus = 'running' | 'ok' | 'error';

/** Paso visible en la traza del agente. Guarda datos, no textos de interfaz. */
export interface TraceStep {
  id: string;
  kind: 'thinking' | 'narration' | 'tool' | 'notice' | 'final' | 'error';
  status: StepStatus;
  /** Solo en `thinking`. */
  iteration?: number;
  /** Texto de `narration` y `notice`, o mensaje de `error`. */
  text?: string;
  /** Solo en `error`. */
  cause?: FailureCause;
  /** Solo en `tool`. */
  toolName?: string;
  input?: Record<string, unknown>;
  output?: unknown;
  durationMs?: number;
  rag?: RagSearch;
}

/** Estado de la conversación y de la ejecución en curso. */
export interface RunState {
  sessionId: string | null;
  messages: ChatMessage[];
  trace: TraceStep[];
  tokens: { input: number; output: number };
  lastRun: RunStats | null;
}

export const initialRunState: RunState = {
  sessionId: null,
  messages: [],
  trace: [],
  tokens: { input: 0, output: 0 },
  lastRun: null,
};

/** Genera el id de los pasos que el servidor no identifica. Se inyecta para que el reducer sea puro. */
export type IdFactory = () => string;

/** El usuario envía un mensaje: se añade al chat y se limpia la traza del turno anterior. */
export function startRun(state: RunState, message: string): RunState {
  return {
    ...state,
    messages: [...state.messages, { role: 'user', text: message }],
    trace: [],
    tokens: { input: 0, output: 0 },
    lastRun: null,
  };
}

/** Estado siguiente tras un evento del agente. Función pura: no toca nada de fuera. */
export function applyEvent(state: RunState, event: AgentEvent, newId: IdFactory): RunState {
  switch (event.type) {
    case 'run_started':
      return { ...state, sessionId: event.sessionId };
    case 'thinking':
      return pushStep(state, {
        id: `think-${event.iteration}`,
        kind: 'thinking',
        iteration: event.iteration,
        status: 'running',
      });
    case 'usage':
      return { ...state, tokens: { input: event.inputTokens, output: event.outputTokens } };
    case 'narration':
      return pushStep(state, { id: newId(), kind: 'narration', text: event.text, status: 'ok' });
    case 'tool_call':
      return pushStep(state, {
        id: event.id,
        kind: 'tool',
        toolName: event.name,
        input: event.input,
        status: 'running',
      });
    case 'tool_result':
      return {
        ...state,
        trace: state.trace.map((step) =>
          step.id === event.id
            ? {
                ...step,
                output: event.output,
                status: event.isError ? 'error' : 'ok',
                durationMs: event.durationMs,
                rag: event.rag,
              }
            : step,
        ),
      };
    case 'notice':
      return addMessage(
        pushStep(state, { id: newId(), kind: 'notice', text: event.text, status: 'ok' }),
        { role: 'notice', text: event.text },
      );
    case 'final':
      return addMessage(pushStep(state, { id: newId(), kind: 'final', status: 'ok' }), {
        role: 'agent',
        text: event.text,
      });
    case 'error':
      return fail(state, 'agent', event.message, newId);
    case 'done':
      return { ...state, lastRun: event.stats };
    case 'trip':
      // El viaje guardado no es estado de la conversación: lo recoge el store de viajes.
      return state;
  }
}

/** No se ha podido contactar con el servidor (red caída, backend parado, demasiadas peticiones). */
export function connectionFailed(state: RunState, message: string, newId: IdFactory): RunState {
  return fail(state, 'connection', message, newId);
}

export function toolSteps(trace: TraceStep[]): TraceStep[] {
  return trace.filter((step) => step.kind === 'tool');
}

export function thinkingCount(trace: TraceStep[]): number {
  return trace.filter((step) => step.kind === 'thinking').length;
}

function fail(state: RunState, cause: FailureCause, message: string, newId: IdFactory): RunState {
  return addMessage(
    pushStep(state, { id: newId(), kind: 'error', cause, text: message, status: 'error' }),
    { role: 'failure', cause, text: message },
  );
}

/** Añade un paso. El "razonando" anterior deja de girar en cuanto llega lo siguiente. */
function pushStep(state: RunState, step: TraceStep): RunState {
  const settled = state.trace.map((s) =>
    s.kind === 'thinking' && s.status === 'running' ? { ...s, status: 'ok' as const } : s,
  );
  return { ...state, trace: [...settled, step] };
}

function addMessage(state: RunState, message: ChatMessage): RunState {
  return { ...state, messages: [...state.messages, message] };
}
