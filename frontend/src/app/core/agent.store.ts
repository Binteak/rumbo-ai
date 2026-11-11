import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { ApiService } from './api.service';
import {
  AgentEvent,
  ChatMessage,
  ChatMode,
  GlobalStats,
  Health,
  RagSearch,
  RunStats,
  TraceStep,
  Trip,
  Usage,
} from './models';

const MODE_KEY = 'rumbo.mode';

function loadMode(): ChatMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'demo' ? 'demo' : 'real';
  } catch {
    return 'real';
  }
}

/** Nombres de los proveedores de modelo tal y como se muestran en la cabecera. */
const PROVIDER_LABELS: Record<string, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  groq: 'Groq',
  huggingface: 'Hugging Face',
  openrouter: 'OpenRouter',
  deepseek: 'DeepSeek',
};

export const TOOL_LABELS: Record<string, string> = {
  search_destinations: 'Buscar destinos',
  get_climate: 'Consultar clima',
  estimate_budget: 'Calcular presupuesto',
  build_itinerary: 'Crear itinerario',
  search_travel_guides: 'Buscar en las guías (RAG)',
  save_trip: 'Guardar viaje',
};

/** Estado de la aplicación con signals: conversación, traza del agente y viajes. */
@Injectable({ providedIn: 'root' })
export class AgentStore {
  private readonly api = inject(ApiService);
  private sub?: Subscription;

  readonly health = signal<Health | null>(null);
  readonly usage = signal<Usage | null>(null);
  readonly messages = signal<ChatMessage[]>([]);
  readonly trace = signal<TraceStep[]>([]);
  readonly running = signal(false);
  readonly tokens = signal({ input: 0, output: 0 });
  readonly lastRun = signal<RunStats | null>(null);
  readonly trips = signal<Trip[]>([]);
  readonly selectedTrip = signal<Trip | null>(null);
  readonly stats = signal<GlobalStats | null>(null);
  readonly sessionId = signal<string | null>(null);
  /** Modo elegido en la interfaz: el modelo real o el demo (se recuerda en el navegador). */
  readonly preferredMode = signal<ChatMode>(loadMode());

  /** True si el backend tiene un modelo real configurado (Gemini, Groq o Claude). */
  readonly realAvailable = computed(() => {
    const mode = this.usage()?.mode ?? this.health()?.mode;
    return !!mode && mode !== 'demo';
  });
  /** "gemini" → "Gemini", "huggingface" → "Hugging Face". */
  readonly providerLabel = computed(() => {
    const mode = this.usage()?.mode ?? this.health()?.mode ?? '';
    return mode ? (PROVIDER_LABELS[mode] ?? mode[0].toUpperCase() + mode.slice(1)) : 'IA real';
  });
  /** Modo con el que se enviará el próximo mensaje. */
  readonly effectiveMode = computed<ChatMode>(() =>
    this.realAvailable() && this.preferredMode() === 'real' ? 'real' : 'demo',
  );

  /** True si la próxima respuesta será del modo demo (sin modelo configurado o con el cupo agotado). */
  readonly isDemo = computed(() => {
    if (this.effectiveMode() === 'demo') return true;
    const u = this.usage();
    return u ? !u.real_ai : this.health()?.mode === 'demo';
  });
  /** "openai/gpt-oss-120b" → "gpt-oss-120b". */
  readonly modelLabel = computed(() => (this.usage()?.model ?? this.health()?.model ?? '').split('/').pop() ?? '');
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
    this.api.usage().subscribe({ next: (u) => this.usage.set(u), error: () => this.usage.set(null) });
  }

  setMode(mode: ChatMode): void {
    this.preferredMode.set(mode);
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* sin almacenamiento disponible: la elección dura lo que la pestaña */
    }
  }

  send(text: string): void {
    const message = text.trim();
    if (!message || this.running()) return;
    this.messages.update((m) => [...m, { role: 'user', text: message }]);
    this.trace.set([]);
    this.tokens.set({ input: 0, output: 0 });
    this.lastRun.set(null);
    this.running.set(true);

    this.sub = this.api.chat(message, this.sessionId(), this.effectiveMode()).subscribe({
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
            s.id === event.id
              ? {
                  ...s,
                  output: event.output,
                  status: event.is_error ? 'error' : 'ok',
                  duration_ms: event.duration_ms,
                  rag: event.name === 'search_travel_guides' && !event.is_error ? (event.output as RagSearch) : undefined,
                }
              : s,
          ),
        );
        break;
      case 'notice':
        this.finishThinking();
        this.pushStep({ id: crypto.randomUUID(), kind: 'notice', title: event.text, status: 'ok' });
        this.messages.update((m) => [...m, { role: 'notice', text: event.text }]);
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
