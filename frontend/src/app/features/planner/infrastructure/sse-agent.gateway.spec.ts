import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom, toArray } from 'rxjs';
import { API_BASE } from '../../../core/config/api-base.token';
import { SseAgentGateway } from './sse-agent.gateway';

/** Respuesta de streaming como la del backend: el cuerpo llega en varios trozos. */
function streamResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status });
}

describe('SseAgentGateway', () => {
  let gateway: SseAgentGateway;
  let http: HttpTestingController;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE, useValue: '/api' },
        SseAgentGateway,
      ],
    });
    gateway = TestBed.inject(SseAgentGateway);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.unstubAllGlobals();
  });

  it('POST /api/chat con el mismo cuerpo que espera el backend', async () => {
    fetchMock.mockResolvedValue(streamResponse([]));

    await firstValueFrom(gateway.send('3 días en Lisboa', 's1', 'demo').pipe(toArray()));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/chat');
    expect(init.method).toBe('POST');
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body)).toEqual({
      message: '3 días en Lisboa',
      session_id: 's1',
      mode: 'demo',
    });
  });

  it('emite los eventos del stream en orden, aunque lleguen partidos', async () => {
    fetchMock.mockResolvedValue(
      streamResponse([
        'data: {"type":"run_started","run_id":"r1","session_id":"s1","mode":"demo","model":"rumbo-demo"}\n\ndata: {"type":"thin',
        'king","iteration":1}\n\n',
        'data: {"type":"final","text":"Hecho"}\n\n',
      ]),
    );

    const events = await firstValueFrom(gateway.send('hola', null, 'real').pipe(toArray()));

    expect(events).toEqual([
      { type: 'run_started', runId: 'r1', sessionId: 's1', provider: 'demo', model: 'rumbo-demo' },
      { type: 'thinking', iteration: 1 },
      { type: 'final', text: 'Hecho' },
    ]);
  });

  it('explica el 429 del anti-flood con un mensaje para el usuario', async () => {
    fetchMock.mockResolvedValue(streamResponse([], 429));

    await expect(firstValueFrom(gateway.send('hola', null, 'real'))).rejects.toThrow(
      'Demasiadas peticiones seguidas. Espera un minuto y vuelve a intentarlo.',
    );
  });

  it('falla con el código de estado si el servidor responde con error', async () => {
    fetchMock.mockResolvedValue(streamResponse([], 500));

    await expect(firstValueFrom(gateway.send('hola', null, 'real'))).rejects.toThrow('Error 500');
  });

  it('cancelar la suscripción aborta la petición', async () => {
    let signal: AbortSignal | undefined;
    fetchMock.mockImplementation((_url: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return new Promise<Response>(() => undefined);
    });

    gateway.send('hola', null, 'real').subscribe().unsubscribe();

    expect(signal?.aborted).toBe(true);
  });

  it('POST /api/sessions/:id/reset olvida la conversación', () => {
    let done = false;
    gateway.resetSession('s1').subscribe(() => (done = true));

    const request = http.expectOne({ method: 'POST', url: '/api/sessions/s1/reset' });
    expect(request.request.body).toEqual({});
    request.flush({ status: 'reset' });

    expect(done).toBe(true);
  });
});
