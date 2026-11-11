import { DecimalPipe, PercentPipe } from '@angular/common';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { SystemStatusStore } from '../../core/status/application/system-status.store';
import { DEMO_PROVIDER } from '../../core/status/domain/system-status';
import { ChatStore } from '../../features/planner/application/chat.store';
import { providerLabel } from './provider-label';

/** Cabecera fija: marca, navegación, cifras globales, selector de modo y aviso sobre el servicio. */
@Component({
  selector: 'app-topbar',
  imports: [DecimalPipe, PercentPipe, RouterLink, RouterLinkActive],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
  host: {
    '(document:click)': 'closeInfoIfOutside($event)',
    '(document:keydown.escape)': 'infoOpen.set(false)',
  },
})
export class Topbar {
  protected readonly status = inject(SystemStatusStore);
  protected readonly chat = inject(ChatStore);
  protected readonly demoProvider = DEMO_PROVIDER;

  protected readonly providerLabel = computed(() => providerLabel(this.status.provider()));

  /** Panel de ayuda: explica que el backend gratuito se duerme y cómo despertarlo. */
  protected readonly infoOpen = signal(false);
  private readonly info = viewChild<ElementRef<HTMLElement>>('info');

  protected readonly modeHint = computed(() => {
    const usage = this.status.usage();
    if (this.status.demoOnly() && this.status.realAvailable()) {
      return 'En el móvil Rumbo funciona en modo demo: el agente responde con reglas, sin coste.';
    }
    if (this.status.preferredMode() === 'demo' && this.status.realAvailable()) {
      return 'Has elegido el modo demo: el agente responde con reglas y no gasta cupo de IA real.';
    }
    if (!usage || usage.provider === DEMO_PROVIDER) {
      return 'Sin modelo configurado: el agente funciona con reglas, sin coste.';
    }
    const { hour = 0, day = 0 } = usage.remaining ?? {};
    return `Modelo gratuito con límites: ${hour} consultas esta hora y ${day} hoy. Después, modo demo.`;
  });

  protected reload(): void {
    location.reload();
  }

  protected closeInfoIfOutside(event: Event): void {
    if (!this.infoOpen()) return;
    if (!this.info()?.nativeElement.contains(event.target as Node)) this.infoOpen.set(false);
  }
}
