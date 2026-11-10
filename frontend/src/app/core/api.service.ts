import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { AgentEvent, ChatMode, GlobalStats, Health, Trip, Usage } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBase;

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/health`);
  }

  usage(): Observable<Usage> {
    return this.http.get<Usage>(`${this.base}/usage`);
  }

  trips(): Observable<Trip[]> {
    return this.http.get<Trip[]>(`${this.base}/trips`);
  }

  deleteTrip(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/trips/${id}`);
  }

  stats(): Observable<GlobalStats> {
    return this.http.get<GlobalStats>(`${this.base}/stats`);
  }

  resetSession(sessionId: string): Observable<unknown> {
    return this.http.post(`${this.base}/sessions/${sessionId}/reset`, {});
  }

  /**
   * Envía un mensaje y emite cada evento del agente en cuanto llega (Server-Sent Events sobre POST).
   * Se usa fetch + ReadableStream porque EventSource solo admite GET.
   */
  chat(message: string, sessionId: string | null, mode: ChatMode = 'real'): Observable<AgentEvent> {
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
          throw new Error('Demasiadas peticiones seguidas. Espera un minuto y vuelve a intentarlo.');
        }
        if (!res.ok || !res.body) {
          throw new Error(`Error ${res.status} al contactar con el agente`);
        }
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          const chunks = buffer.split('\n\n');
          buffer = chunks.pop() ?? '';
          for (const chunk of chunks) {
            const line = chunk.split('\n').find((l) => l.startsWith('data: '));
            if (line) subscriber.next(JSON.parse(line.slice(6)) as AgentEvent);
          }
        }
        subscriber.complete();
      })().catch((err) => {
        if (!controller.signal.aborted) subscriber.error(err);
      });

      return () => controller.abort();
    });
  }
}
