import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { AgentStore } from './agent.store';
import { ApiService } from './api.service';
import { AgentEvent, Trip } from './models';

describe('AgentStore', () => {
  let events: Subject<AgentEvent>;
  let store: AgentStore;

  beforeEach(() => {
    events = new Subject<AgentEvent>();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ApiService,
          useValue: {
            chat: () => events,
            trips: () => of([]),
            stats: () => of(null),
            health: () => of({ status: 'ok', mode: 'demo', model: 'rumbo-demo' }),
          },
        },
      ],
    });
    store = TestBed.inject(AgentStore);
  });

  it('construye la traza a partir de los eventos del agente', () => {
    store.send('3 días en Seúl');
    expect(store.running()).toBe(true);

    events.next({ type: 'run_started', run_id: 'r1', session_id: 's1', mode: 'demo', model: 'rumbo-demo' });
    events.next({ type: 'thinking', iteration: 1 });
    events.next({ type: 'tool_call', id: 't1', name: 'get_climate', input: { destination_id: 'seul', month: 5 } });
    events.next({ type: 'tool_result', id: 't1', name: 'get_climate', output: { error: 'x' }, is_error: true, duration_ms: 1 });
    events.next({ type: 'trip', trip: { id: 9, title: 'Seúl' } as Trip });
    events.next({ type: 'final', text: 'Hecho' });
    events.complete();

    expect(store.sessionId()).toBe('s1');
    const tool = store.trace().find((s) => s.id === 't1');
    expect(tool?.title).toBe('Consultar clima');
    expect(tool?.status).toBe('error');
    expect(store.trace().some((s) => s.kind === 'thinking' && s.status === 'running')).toBe(false);
    expect(store.selectedTrip()?.id).toBe(9);
    expect(store.messages().map((m) => m.role)).toEqual(['user', 'agent']);
    expect(store.running()).toBe(false);
  });

  it('ignora mensajes vacíos', () => {
    store.send('   ');
    expect(store.messages()).toEqual([]);
  });
});
