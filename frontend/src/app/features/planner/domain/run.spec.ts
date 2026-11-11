import { aTrip } from '../../trips/testing/trip.fixture';
import { AgentEvent } from './agent-event';
import {
  RunState,
  applyEvent,
  connectionFailed,
  initialRunState,
  startRun,
  thinkingCount,
  toolSteps,
} from './run';

/** Ids deterministas: el reducer es puro y se prueba sin Angular. */
function ids(): () => string {
  let n = 0;
  return () => `id-${++n}`;
}

function play(events: AgentEvent[], from: RunState = initialRunState): RunState {
  const newId = ids();
  return events.reduce((state, event) => applyEvent(state, event, newId), from);
}

describe('reducer de la ejecución del agente', () => {
  it('al enviar un mensaje lo añade al chat y limpia la traza del turno anterior', () => {
    const previous = play([
      { type: 'thinking', iteration: 1 },
      { type: 'usage', inputTokens: 10, outputTokens: 5 },
      { type: 'final', text: 'Listo' },
    ]);

    const next = startRun(previous, 'Otro viaje');

    expect(next.messages.map((m) => m.role)).toEqual(['agent', 'user']);
    expect(next.trace).toEqual([]);
    expect(next.tokens).toEqual({ input: 0, output: 0 });
  });

  it('guarda la sesión que asigna el servidor', () => {
    const state = play([
      { type: 'run_started', runId: 'r1', sessionId: 's1', provider: 'demo', model: 'rumbo-demo' },
    ]);
    expect(state.sessionId).toBe('s1');
  });

  it('el paso "razonando" deja de girar cuando llega el siguiente', () => {
    const state = play([
      { type: 'thinking', iteration: 1 },
      { type: 'tool_call', id: 't1', name: 'get_climate', input: { month: 5 } },
    ]);

    expect(state.trace.map((s) => [s.kind, s.status])).toEqual([
      ['thinking', 'ok'],
      ['tool', 'running'],
    ]);
  });

  it('completa el paso de la herramienta con su resultado, sea correcto o un error', () => {
    const state = play([
      { type: 'tool_call', id: 'ok', name: 'get_climate', input: {} },
      { type: 'tool_call', id: 'ko', name: 'estimate_budget', input: {} },
      {
        type: 'tool_result',
        id: 'ok',
        name: 'get_climate',
        output: { t: 18 },
        isError: false,
        durationMs: 2,
      },
      {
        type: 'tool_result',
        id: 'ko',
        name: 'estimate_budget',
        output: { error: 'x' },
        isError: true,
        durationMs: 1,
      },
    ]);

    expect(state.trace.find((s) => s.id === 'ok')).toMatchObject({
      status: 'ok',
      output: { t: 18 },
      durationMs: 2,
    });
    expect(state.trace.find((s) => s.id === 'ko')).toMatchObject({
      status: 'error',
      toolName: 'estimate_budget',
    });
  });

  it('un aviso aparece en la traza y en el chat', () => {
    const state = play([{ type: 'notice', text: 'Respondo en modo demo.' }]);

    expect(state.trace[0]).toMatchObject({ kind: 'notice', text: 'Respondo en modo demo.' });
    expect(state.messages).toEqual([{ role: 'notice', text: 'Respondo en modo demo.' }]);
  });

  it('la respuesta final cierra la traza y se añade al chat', () => {
    const state = play([
      { type: 'thinking', iteration: 1 },
      { type: 'final', text: 'Hecho' },
    ]);

    expect(state.trace.at(-1)).toMatchObject({ kind: 'final', status: 'ok' });
    expect(state.trace.some((s) => s.status === 'running')).toBe(false);
    expect(state.messages).toEqual([{ role: 'agent', text: 'Hecho' }]);
  });

  it('distingue un error del agente de un fallo de conexión', () => {
    const agent = play([{ type: 'error', message: 'ValueError: x' }]);
    const network = connectionFailed(initialRunState, 'Failed to fetch', ids());

    expect(agent.messages).toEqual([{ role: 'failure', cause: 'agent', text: 'ValueError: x' }]);
    expect(agent.trace[0]).toMatchObject({ kind: 'error', cause: 'agent', status: 'error' });
    expect(network.messages).toEqual([
      { role: 'failure', cause: 'connection', text: 'Failed to fetch' },
    ]);
  });

  it('acumula tokens y guarda el resumen al terminar', () => {
    const stats = {
      iterations: 2,
      toolCalls: 3,
      toolErrors: 0,
      inputTokens: 900,
      outputTokens: 120,
      durationMs: 1500,
      status: 'completed',
    };
    const state = play([
      { type: 'usage', inputTokens: 900, outputTokens: 120 },
      { type: 'done', stats },
    ]);

    expect(state.tokens).toEqual({ input: 900, output: 120 });
    expect(state.lastRun).toEqual(stats);
  });

  it('el viaje guardado no cambia el estado de la conversación', () => {
    const before = play([{ type: 'thinking', iteration: 1 }]);
    expect(applyEvent(before, { type: 'trip', trip: aTrip() }, ids())).toBe(before);
  });

  it('no modifica el estado anterior', () => {
    const before = play([{ type: 'thinking', iteration: 1 }]);
    const snapshot = structuredClone(before);

    applyEvent(before, { type: 'final', text: 'Hecho' }, ids());

    expect(before).toEqual(snapshot);
  });

  it('cuenta herramientas y pasos de razonamiento', () => {
    const { trace } = play([
      { type: 'thinking', iteration: 1 },
      { type: 'tool_call', id: 'a', name: 'get_climate', input: {} },
      { type: 'thinking', iteration: 2 },
      { type: 'tool_call', id: 'b', name: 'save_trip', input: {} },
    ]);

    expect(toolSteps(trace).map((s) => s.id)).toEqual(['a', 'b']);
    expect(thinkingCount(trace)).toBe(2);
  });
});
