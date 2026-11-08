import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from './api.service';
import { AgentEvent, ChatMessage, GlobalStats, Health, RunStats, TraceStep, Trip } from './models';

export const TOOL_LABELS: Record<string, string> = {
  search_destinations: 'Buscar destinos',
  get_climate: 'Consultar clima',
  estimate_budget: 'Calcular presupuesto',
  build_itinerary: 'Crear itinerario',
  save_trip: 'Guardar viaje',
};

/** Estado de la aplicación con signals: conversación, traza del agente y viajes. */
@Injectable({ providedIn: 'root' })
export class AgentStore {
  private readonly api = inject(ApiService);
  private sub?: Subscription;

  readonly health = signal<Health | null>(null);
  readonly messages = signal<ChatMessage[]>([]);
  readonly trace = signal<TraceStep[]>([]);
  readonly running = signal(false);
  readonly tokens = signal({ input: 0, output: 0 });
  readonly lastRun = signal<RunStats | null>(null);
  readonly trips = signal<Trip[]>([]);
  readonly selectedTrip = signal<Trip | null>(null);
  readonly stats = signal<GlobalStats | null>(null);
  readonly sessionId = signal<string | null>(null);

  readonly isDemo = computed(() => this.health()?.mode === 'demo');
  readonly toolSteps = computed(() => this.trace().filter((s) => s.kind === 'tool'));

  init(): void {
    this.api.health().subscribe({ next: (h) => this.health.set(h), error: () => this.health.set(null) });
    this.refresh();
  }

  refresh(): void {
    this.api.trips().subscribe((t) => {
      this.trips.set(t);
      if (!this.selectedTrip() && t.length) this.selectedTrip.set(t[0]);
    });
    this.api.stats().subscribe((s) => this.stats.set(s));
  }

  send(text: string): void {
    const message = text.trim();
    if (!message || this.running()) return;
    this.messages.update((m) => [...m, { role: 'user', text: message }]);
    this.trace.set([]);
    this.tokens.set({ input: 0, output: 0 });
    this.lastRun.set(null);
    this.running.set(true);

    this.sub = this.api.chat(message, this.sessionId()).subscribe({
      next: (event) => this.handle(event),
      error: (err: Error) => {
        this.pushStep({ id: crypto.randomUUID(), kind: 'error', title: 'Error de conexión', detail: err.message, status: 'error' });
        this.messages.update((m) => [...m, { role: 'agent', text: 'No he podido contactar con el servidor. ¿Está el backend arrancado?' }]);
        this.running.set(false);
      },
      complete: () => {
        this.running.set(false);
        this.refresh();
      },
    });
  }

  stop(): void {
    this.sub?.unsubscribe();
    this.running.set(false);
  }

  newConversation(): void {
    const id = this.sessionId();
    if (id) this.api.resetSession(id).subscribe();
    this.stop();
    this.sessionId.set(null);
    this.messages.set([]);
    this.trace.set([]);
    this.lastRun.set(null);
  }

  removeTrip(trip: Trip): void {
    this.api.deleteTrip(trip.id).subscribe(() => {
      if (this.selectedTrip()?.id === trip.id) this.selectedTrip.set(null);
      this.refresh();
    });
  }

  private handle(event: AgentEvent): void {
    switch (event.type) {
      case 'run_started':
        this.sessionId.set(event.session_id);
        break;
      case 'thinking':
        this.finishThinking();
        this.pushStep({ id: `think-${event.iteration}`, kind: 'thinking', title: `Razonando · paso ${event.iteration}`, status: 'running' });
        break;
      case 'usage':
        this.tokens.set({ input: event.input_tokens, output: event.output_tokens });
        break;
      case 'narration':
        this.finishThinking();
        this.pushStep({ id: crypto.randomUUID(), kind: 'narration', title: event.text, status: 'ok' });
        break;
      case 'tool_call':
        this.finishThinking();
        this.pushStep({
          id: event.id,
          kind: 'tool',
          title: TOOL_LABELS[event.name] ?? event.name,
          detail: event.name,
          input: event.input,
          status: 'running',
        });
        break;
      case 'tool_result':
        this.trace.update((steps) =>
          steps.map((s) =>
            s.id === event.id ? { ...s, output: event.output, status: event.is_error ? 'error' : 'ok', duration_ms: event.duration_ms } : s,
          ),
        );
        break;
      case 'trip':
        this.selectedTrip.set(event.trip);
        break;
      case 'final':
        this.finishThinking();
        this.pushStep({ id: crypto.randomUUID(), kind: 'final', title: 'Respuesta final', status: 'ok' });
        this.messages.update((m) => [...m, { role: 'agent', text: event.text }]);
        break;
      case 'error':
        this.finishThinking();
        this.pushStep({ id: crypto.randomUUID(), kind: 'error', title: 'Error', detail: event.message, status: 'error' });
        this.messages.update((m) => [...m, { role: 'agent', text: `Algo ha fallado: ${event.message}` }]);
        break;
      case 'done':
        this.lastRun.set(event.stats);
        break;
    }
  }

  private pushStep(step: TraceStep): void {
    this.trace.update((s) => [...s, step]);
  }

  /** El paso "razonando" deja de girar cuando llega lo siguiente. */
  private finishThinking(): void {
    this.trace.update((steps) => steps.map((s) => (s.kind === 'thinking' && s.status === 'running' ? { ...s, status: 'ok' } : s)));
  }
}
