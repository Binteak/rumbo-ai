import { ComponentFixture, TestBed } from '@angular/core/testing';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { RagSearch } from '../../domain/agent-event';
import { TraceStep } from '../../domain/run';
import { stepTitle } from './step-title';
import { TracePanel } from './trace-panel';

registerLocaleData(localeEs);

const rag: RagSearch = {
  query: '¿Necesito visado para Japón?',
  destinationId: 'kioto',
  retrieval: 'hybrid',
  expandedTerms: [],
  timingsMs: {},
  results: [
    {
      source: 'guides/kioto.md',
      destinationId: 'kioto',
      destination: 'Kioto',
      section: 'Documentación y entrada',
      text: 'Sin visado hasta 90 días.',
      score: 0.12,
      match: { bm25Rank: 1, vectorRank: 2, vectorSimilarity: 0.3 },
    },
  ],
};

describe('TracePanel', () => {
  let fixture: ComponentFixture<TracePanel>;
  let el: HTMLElement;

  async function render(inputs: Record<string, unknown>): Promise<void> {
    for (const [name, value] of Object.entries(inputs)) fixture.componentRef.setInput(name, value);
    await fixture.whenStable();
  }

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [{ provide: LOCALE_ID, useValue: 'es' }] });
    fixture = TestBed.createComponent(TracePanel);
    el = fixture.nativeElement;
  });

  it('sin pasos explica para qué sirve el panel', async () => {
    await render({ trace: [] });

    expect(el.querySelector('.placeholder')).not.toBeNull();
    expect(el.querySelector('.live')).toBeNull();
  });

  it('pone título legible a cada paso', () => {
    expect(stepTitle({ id: '1', kind: 'thinking', status: 'running', iteration: 2 })).toBe(
      'Razonando · paso 2',
    );
    expect(stepTitle({ id: '2', kind: 'tool', status: 'ok', toolName: 'get_climate' })).toBe(
      'Consultar clima',
    );
    expect(stepTitle({ id: '3', kind: 'tool', status: 'ok', toolName: 'nueva_tool' })).toBe(
      'nueva_tool',
    );
    expect(stepTitle({ id: '4', kind: 'error', status: 'error', cause: 'connection' })).toBe(
      'Error de conexión',
    );
    expect(stepTitle({ id: '5', kind: 'final', status: 'ok' })).toBe('Respuesta final');
  });

  it('pinta los pasos con su estado y las métricas del turno en curso', async () => {
    const trace: TraceStep[] = [
      { id: 'think-1', kind: 'thinking', status: 'ok', iteration: 1 },
      {
        id: 't1',
        kind: 'tool',
        status: 'error',
        toolName: 'get_climate',
        input: { month: 5 },
        output: { error: 'x' },
        durationMs: 3,
      },
    ];
    await render({ trace, running: true, tokens: { input: 1200, output: 34 } });

    const steps = el.querySelectorAll('.step');
    expect(steps.length).toBe(2);
    expect(steps[1].classList.contains('error')).toBe(true);
    expect(steps[1].querySelector('.fn')?.textContent).toBe('get_climate()');
    expect(steps[1].querySelector('small')?.textContent).toBe('3 ms');
    expect(el.querySelector('.live')).not.toBeNull();

    const metrics = [...el.querySelectorAll('.metrics strong')].map((m) => m.textContent?.trim());
    expect(metrics).toEqual(['1', '1', '1.234', '—']);
  });

  it('al terminar muestra los pasos y el tiempo del resumen', async () => {
    await render({
      trace: [],
      lastRun: {
        iterations: 4,
        toolCalls: 5,
        toolErrors: 0,
        inputTokens: 0,
        outputTokens: 0,
        durationMs: 2340,
        status: 'completed',
      },
    });

    const metrics = [...el.querySelectorAll('.metrics strong')].map((m) => m.textContent?.trim());
    expect(metrics[0]).toBe('4');
    expect(metrics[3]).toBe('2,3 s');
  });

  it('enseña las fuentes recuperadas por el RAG', async () => {
    await render({
      trace: [{ id: 'g1', kind: 'tool', status: 'ok', toolName: 'search_travel_guides', rag }],
    });

    expect(el.querySelector('.rag-meta')?.textContent).toContain('Búsqueda híbrida');
    expect(el.querySelector('.rag-meta')?.textContent).toContain('filtro: kioto');
    expect(el.querySelector('.source-head strong')?.textContent).toBe(
      'Kioto · Documentación y entrada',
    );
    expect([...el.querySelectorAll('.ranks i')].map((i) => i.textContent)).toEqual([
      'BM25 #1',
      'vector #2',
    ]);
  });

  it('avisa cuando las guías no cubren la pregunta', async () => {
    await render({
      trace: [
        {
          id: 'g1',
          kind: 'tool',
          status: 'ok',
          toolName: 'search_travel_guides',
          rag: { ...rag, results: [] },
        },
      ],
    });

    expect(el.querySelector('.rag-empty')).not.toBeNull();
  });
});
