import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { SystemStatusStore } from '../../../core/status/application/system-status.store';
import { TripsStore } from '../../trips/application/trips.store';
import { AgentEvent } from '../domain/agent-event';
import {
  applyEvent,
  connectionFailed,
  initialRunState,
  startRun,
  thinkingCount,
  toolSteps,
} from '../domain/run';
import { AgentGateway } from './agent.gateway';

const newId = (): string => crypto.randomUUID();

/** Caso de uso "hablar con el agente": envía el mensaje y aplica cada evento al estado. */
@Injectable({ providedIn: 'root' })
export class ChatStore {
  private readonly gateway = inject(AgentGateway);
  private readonly status = inject(SystemStatusStore);
  private readonly trips = inject(TripsStore);
  private readonly state = signal(initialRunState);
  private subscription?: Subscription;

  readonly running = signal(false);
  readonly sessionId = computed(() => this.state().sessionId);
  readonly messages = computed(() => this.state().messages);
  readonly trace = computed(() => this.state().trace);
  readonly tokens = computed(() => this.state().tokens);
  readonly lastRun = computed(() => this.state().lastRun);
  readonly toolCount = computed(() => toolSteps(this.trace()).length);
  readonly thinkingCount = computed(() => thinkingCount(this.trace()));

  send(text: string): void {
    const message = text.trim();
    if (!message || this.running()) return;
    this.state.update((state) => startRun(state, message));
    this.running.set(true);

    this.subscription = this.gateway
      .send(message, this.sessionId(), this.status.effectiveMode())
      .subscribe({
        next: (event) => this.handle(event),
        error: (err: Error) => {
          this.state.update((state) => connectionFailed(state, err.message, newId));
          this.running.set(false);
        },
        complete: () => {
          this.running.set(false);
          this.trips.load();
          this.status.refresh();
        },
      });
  }

  stop(): void {
    this.subscription?.unsubscribe();
    this.running.set(false);
  }

  newConversation(): void {
    const id = this.sessionId();
    if (id) this.gateway.resetSession(id).subscribe();
    this.stop();
    this.state.set(initialRunState);
  }

  private handle(event: AgentEvent): void {
    this.state.update((state) => applyEvent(state, event, newId));
    if (event.type === 'trip') this.trips.select(event.trip);
  }
}
