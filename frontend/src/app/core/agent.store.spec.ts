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
            usage: () => of({ mode: 'groq', model: 'openai/gpt-oss-120b', real_ai: true, remaining: { hour: 5, day: 15 } }),
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

  it('guarda las fuentes del RAG en el paso de la herramienta', () => {
    store.send('¿Necesito visado para Japón?');
    const rag = {
      query: '¿Necesito visado para Japón?',
      destination_id: 'kioto',
      retrieval: 'hybrid',
      expanded_terms: [],
      timings_ms: { bm25: 0.2, vector: 0.4 },
      results: [
        {
          source: 'guides/kioto.md',
          destination_id: 'kioto',
          destination: 'Kioto',
          section: 'Documentación y entrada',
          text: 'Sin visado hasta 90 días.',
          score: 0.12,
          match: { bm25_rank: 1, vector_rank: 1, vector_similarity: 0.3 },
        },
      ],
    };
    events.next({ type: 'tool_call', id: 'g1', name: 'search_travel_guides', input: { query: rag.query } });
    events.next({ type: 'tool_result', id: 'g1', name: 'search_travel_guides', output: rag, is_error: false, duration_ms: 2 });

    const step = store.trace().find((s) => s.id === 'g1');
    expect(step?.title).toBe('Buscar en las guías (RAG)');
    expect(step?.rag?.results[0].section).toBe('Documentación y entrada');
  });

  it('muestra el aviso de paso al modo demo en el chat y en la traza', () => {
    store.init();
    expect(store.isDemo()).toBe(false);
    expect(store.modelLabel()).toBe('gpt-oss-120b');

    store.send('hola');
    events.next({ type: 'notice', text: 'Has usado tus consultas con IA real: respondo en modo demo.' });
    expect(store.messages().map((m) => m.role)).toEqual(['user', 'notice']);
    expect(store.trace().some((s) => s.kind === 'notice')).toBe(true);
  });

  it('ignora mensajes vacíos', () => {
    store.send('   ');
    expect(store.messages()).toEqual([]);
  });
});
