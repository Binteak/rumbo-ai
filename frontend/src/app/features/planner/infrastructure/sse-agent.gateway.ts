import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { API_BASE } from '../../../core/config/api-base.token';
import { ChatMode } from '../../../core/status/domain/system-status';
import { AgentGateway } from '../application/agent.gateway';
import { AgentEvent } from '../domain/agent-event';
import { AgentEventDto, toAgentEvent } from './agent-event.dto';
import { SseParser } from './sse-parser';

/**
 * Adaptador del agente sobre Server-Sent Events enviados por POST.
 * Se usa fetch + ReadableStream porque EventSource solo admite GET.
 */
@Injectable()
export class SseAgentGateway implements AgentGateway {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE);

  send(message: string, sessionId: string | null, mode: ChatMode): Observable<AgentEvent> {
    return new Observable<AgentEvent>((subscriber) => {
      const controller = new AbortController();

      (async () => {
        const res = await fetch(`${this.base}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, session_id: sessionId, mode }),
          signal: controller.signal,
        });
        if (res.status === 429) {
          throw new Error(
            'Demasiadas peticiones seguidas. Espera un minuto y vuelve a intentarlo.',
          );
        }
        if (!res.ok || !res.body) {
          throw new Error(`Error ${res.status} al contactar con el agente`);
        }
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        const parser = new SseParser();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          for (const raw of parser.push(value)) {
            const event = toAgentEvent(raw as AgentEventDto);
            if (event) subscriber.next(event);
          }
        }
        subscriber.complete();
      })().catch((err) => {
        if (!controller.signal.aborted) subscriber.error(err);
      });

      return () => controller.abort();
    });
  }

  resetSession(sessionId: string): Observable<void> {
    return this.http
      .post(`${this.base}/sessions/${sessionId}/reset`, {})
      .pipe(map(() => undefined));
  }
}
