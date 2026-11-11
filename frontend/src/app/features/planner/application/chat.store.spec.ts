import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { PreferencesStorage } from '../../../core/status/application/preferences.storage';
import { StatusGateway } from '../../../core/status/application/status.gateway';
import { SystemStatusStore } from '../../../core/status/application/system-status.store';
import { TripRepository } from '../../trips/application/trip.repository';
import { TripsStore } from '../../trips/application/trips.store';
import { aTrip } from '../../trips/testing/trip.fixture';
import { AgentEvent } from '../domain/agent-event';
import { AgentGateway } from './agent.gateway';
import { ChatStore } from './chat.store';

describe('ChatStore', () => {
  let events: Subject<AgentEvent>;
  let gateway: { send: ReturnType<typeof vi.fn>; resetSession: ReturnType<typeof vi.fn> };
  let listTrips: ReturnType<typeof vi.fn>;
  let store: ChatStore;
  let status: SystemStatusStore;

  beforeEach(() => {
    events = new Subject<AgentEvent>();
    gateway = { send: vi.fn(() => events), resetSession: vi.fn(() => of(undefined)) };
    listTrips = vi.fn(() => of([]));
    // Todos los puertos se sustituyen por dobles: el store se prueba sin red ni navegador.
    TestBed.configureTestingModule({
      providers: [
        { provide: AgentGateway, useValue: gateway },
        { provide: TripRepository, useValue: { list: listTrips } },
        {
          provide: StatusGateway,
          useValue: {
            health: () => of({ status: 'ok', provider: 'demo', model: 'rumbo-demo' }),
            usage: () => of({ provider: 'groq', model: 'openai/gpt-oss-120b', realAi: true }),
            stats: () => of(null),
          },
        },
        {
          provide: PreferencesStorage,
          useValue: { loadMode: () => 'real', saveMode: () => undefined },
        },
      ],
    });
    store = TestBed.inject(ChatStore);
    status = TestBed.inject(SystemStatusStore);
  });

  it('envía con el modo elegido aunque haya un modelo real', () => {
    status.init();

    status.setMode('demo');
    store.send('3 días en Lisboa');
    expect(gateway.send).toHaveBeenLastCalledWith('3 días en Lisboa', null, 'demo');
    store.stop();

    status.setMode('real');
    store.send('3 días en Lisboa');
    expect(gateway.send).toHaveBeenLastCalledWith('3 días en Lisboa', null, 'real');
  });

  it('construye la conversación y la traza a partir de los eventos', () => {
    store.send('3 días en Seúl');
    expect(store.running()).toBe(true);

    events.next({
      type: 'run_started',
      runId: 'r1',
      sessionId: 's1',
      provider: 'demo',
      model: 'rumbo-demo',
    });
    events.next({ type: 'thinking', iteration: 1 });
    events.next({
      type: 'tool_call',
      id: 't1',
      name: 'get_climate',
      input: { destination_id: 'seul', month: 5 },
    });
    events.next({
      type: 'tool_result',
      id: 't1',
      name: 'get_climate',
      output: { error: 'x' },
      isError: true,
      durationMs: 1,
    });
    events.next({ type: 'final', text: 'Hecho' });
    events.complete();

    expect(store.sessionId()).toBe('s1');
    expect(store.trace().find((s) => s.id === 't1')?.status).toBe('error');
    expect(store.toolCount()).toBe(1);
    expect(store.thinkingCount()).toBe(1);
    expect(store.messages().map((m) => m.role)).toEqual(['user', 'agent']);
    expect(store.running()).toBe(false);
  });

  it('muestra en el planificador el viaje que guarda el agente', () => {
    const trip = aTrip({ id: 21 });
    store.send('3 días en Seúl');

    events.next({ type: 'trip', trip });

    expect(TestBed.inject(TripsStore).selected()).toEqual(trip);
  });

  it('al terminar recarga los viajes y el cupo', () => {
    const refresh = vi.spyOn(status, 'refresh');
    store.send('hola');

    events.complete();

    expect(listTrips).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('reutiliza la sesión en el siguiente mensaje', () => {
    store.send('hola');
    events.next({
      type: 'run_started',
      runId: 'r1',
      sessionId: 's1',
      provider: 'demo',
      model: 'rumbo-demo',
    });
    events.complete();

    events = new Subject<AgentEvent>();
    store.send('¿y en junio?');

    expect(gateway.send.mock.lastCall?.slice(0, 2)).toEqual(['¿y en junio?', 's1']);
  });

  it('si no hay conexión lo cuenta en el chat y deja de esperar', () => {
    store.send('hola');

    events.error(new Error('Failed to fetch'));

    expect(store.messages().at(-1)).toEqual({
      role: 'failure',
      cause: 'connection',
      text: 'Failed to fetch',
    });
    expect(store.trace().at(-1)).toMatchObject({ kind: 'error', cause: 'connection' });
    expect(store.running()).toBe(false);
  });

  it('ignora mensajes vacíos y no envía dos a la vez', () => {
    store.send('   ');
    expect(store.messages()).toEqual([]);

    store.send('uno');
    store.send('dos');

    expect(gateway.send).toHaveBeenCalledTimes(1);
  });

  it('detener cancela la petición en curso', () => {
    store.send('hola');
    expect(events.observed).toBe(true);

    store.stop();

    expect(events.observed).toBe(false);
    expect(store.running()).toBe(false);
  });

  it('una conversación nueva olvida la sesión en el servidor y limpia la pantalla', () => {
    store.send('hola');
    events.next({
      type: 'run_started',
      runId: 'r1',
      sessionId: 's1',
      provider: 'demo',
      model: 'rumbo-demo',
    });
    events.next({ type: 'final', text: 'Hecho' });
    events.complete();

    store.newConversation();

    expect(gateway.resetSession).toHaveBeenCalledWith('s1');
    expect(store.sessionId()).toBeNull();
    expect(store.messages()).toEqual([]);
    expect(store.trace()).toEqual([]);
  });
});
