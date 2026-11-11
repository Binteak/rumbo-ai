import { aTrip, aTripDto } from '../../trips/testing/trip.fixture';
import { AgentEventDto, RagSearchDto, toAgentEvent } from './agent-event.dto';

const ragDto: RagSearchDto = {
  query: '¿Necesito visado para Japón?',
  destination_id: 'kioto',
  retrieval: 'hybrid',
  expanded_terms: ['visado'],
  timings_ms: { bm25: 0.2, vector: 0.4 },
  results: [
    {
      source: 'guides/kioto.md',
      destination_id: 'kioto',
      destination: 'Kioto',
      section: 'Documentación y entrada',
      text: 'Sin visado hasta 90 días.',
      score: 0.12,
      match: { bm25_rank: 1, vector_rank: 2, vector_similarity: 0.3 },
    },
  ],
};

describe('traducción de eventos del stream al dominio', () => {
  it('pasa a camelCase el inicio, el uso y el resumen final', () => {
    expect(
      toAgentEvent({
        type: 'run_started',
        run_id: 'r1',
        session_id: 's1',
        mode: 'groq',
        model: 'm',
      }),
    ).toEqual({
      type: 'run_started',
      runId: 'r1',
      sessionId: 's1',
      provider: 'groq',
      model: 'm',
    });
    expect(toAgentEvent({ type: 'usage', input_tokens: 10, output_tokens: 4 })).toEqual({
      type: 'usage',
      inputTokens: 10,
      outputTokens: 4,
    });
    expect(
      toAgentEvent({
        type: 'done',
        stats: {
          iterations: 2,
          tool_calls: 3,
          tool_errors: 1,
          input_tokens: 10,
          output_tokens: 4,
          duration_ms: 900,
          status: 'completed',
        },
      }),
    ).toEqual({
      type: 'done',
      stats: {
        iterations: 2,
        toolCalls: 3,
        toolErrors: 1,
        inputTokens: 10,
        outputTokens: 4,
        durationMs: 900,
        status: 'completed',
      },
    });
  });

  it('deja el resultado de la herramienta sin tocar para enseñarlo en la traza', () => {
    const output = { avg_temp_c: 18 };
    const event = toAgentEvent({
      type: 'tool_result',
      id: 't1',
      name: 'get_climate',
      output,
      is_error: false,
      duration_ms: 2,
    });

    expect(event).toEqual({
      type: 'tool_result',
      id: 't1',
      name: 'get_climate',
      output,
      isError: false,
      durationMs: 2,
      rag: undefined,
    });
  });

  it('extrae las fuentes del RAG de una búsqueda en las guías', () => {
    const event = toAgentEvent({
      type: 'tool_result',
      id: 'g1',
      name: 'search_travel_guides',
      output: ragDto,
      is_error: false,
      duration_ms: 3,
    });

    expect(event?.type === 'tool_result' && event.rag).toEqual({
      query: ragDto.query,
      destinationId: 'kioto',
      retrieval: 'hybrid',
      expandedTerms: ['visado'],
      timingsMs: { bm25: 0.2, vector: 0.4 },
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
    });
  });

  it('no busca fuentes si la búsqueda en las guías ha fallado', () => {
    const event = toAgentEvent({
      type: 'tool_result',
      id: 'g1',
      name: 'search_travel_guides',
      output: { error: 'Destino desconocido' },
      is_error: true,
      duration_ms: 1,
    });

    expect(event?.type === 'tool_result' && event.rag).toBeUndefined();
  });

  it('traduce el viaje guardado', () => {
    expect(toAgentEvent({ type: 'trip', trip: aTripDto() })).toEqual({
      type: 'trip',
      trip: aTrip(),
    });
  });

  it('ignora un tipo de evento que todavía no conoce', () => {
    expect(toAgentEvent({ type: 'heartbeat' } as unknown as AgentEventDto)).toBeNull();
  });
});
