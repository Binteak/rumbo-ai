import { DecimalPipe, PercentPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { SystemStatusStore } from '../../core/status/application/system-status.store';
import { DEMO_PROVIDER } from '../../core/status/domain/system-status';
import { ChatStore } from '../../features/planner/application/chat.store';
import { providerLabel } from './provider-label';

/** Cabecera fija: marca, navegación, cifras globales y selector de modo. */
@Component({
  selector: 'app-topbar',
  imports: [DecimalPipe, PercentPipe, RouterLink, RouterLinkActive],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
})
export class Topbar {
  protected readonly status = inject(SystemStatusStore);
  protected readonly chat = inject(ChatStore);
  protected readonly demoProvider = DEMO_PROVIDER;

  protected readonly providerLabel = computed(() => providerLabel(this.status.provider()));

  protected readonly modeHint = computed(() => {
    const usage = this.status.usage();
    if (this.status.preferredMode() === 'demo' && this.status.realAvailable()) {
      return 'Has elegido el modo demo: el agente responde con reglas y no gasta cupo de IA real.';
    }
    if (!usage || usage.provider === DEMO_PROVIDER) {
      return 'Sin modelo configurado: el agente funciona con reglas, sin coste.';
    }
    const { hour = 0, day = 0 } = usage.remaining ?? {};
    return `Modelo gratuito con límites: ${hour} consultas esta hora y ${day} hoy. Después, modo demo.`;
  });
}
