import { Injectable, computed, inject, signal } from '@angular/core';
import {
  ChatMode,
  GlobalStats,
  Health,
  Usage,
  answersInDemo,
  currentProvider,
  isRealAvailable,
  resolveMode,
  shortModelName,
} from '../domain/system-status';
import { PreferencesStorage } from './preferences.storage';
import { StatusGateway } from './status.gateway';

/** Estado del servicio y modo elegido por el usuario. Las reglas viven en el dominio. */
@Injectable({ providedIn: 'root' })
export class SystemStatusStore {
  private readonly gateway = inject(StatusGateway);
  private readonly preferences = inject(PreferencesStorage);

  readonly health = signal<Health | null>(null);
  readonly usage = signal<Usage | null>(null);
  readonly stats = signal<GlobalStats | null>(null);
  /** Modo elegido en la interfaz (se recuerda entre visitas). */
  readonly preferredMode = signal<ChatMode>(this.preferences.loadMode());

  readonly provider = computed(() => currentProvider(this.usage(), this.health()));
  readonly realAvailable = computed(() => isRealAvailable(this.usage(), this.health()));
  readonly effectiveMode = computed(() => resolveMode(this.realAvailable(), this.preferredMode()));
  readonly isDemo = computed(() =>
    answersInDemo(this.effectiveMode(), this.usage(), this.health()),
  );
  readonly modelLabel = computed(() => shortModelName(this.usage(), this.health()));

  init(): void {
    this.gateway.health().subscribe({
      next: (health) => this.health.set(health),
      error: () => this.health.set(null),
    });
    this.refresh();
  }

  /** Vuelve a pedir lo que cambia tras cada ejecución: estadísticas y cupo. */
  refresh(): void {
    this.gateway.stats().subscribe({
      next: (stats) => this.stats.set(stats),
      error: () => this.stats.set(null),
    });
    this.gateway.usage().subscribe({
      next: (usage) => this.usage.set(usage),
      error: () => this.usage.set(null),
    });
  }

  setMode(mode: ChatMode): void {
    this.preferredMode.set(mode);
    this.preferences.saveMode(mode);
  }
}
