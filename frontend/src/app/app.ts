import { DecimalPipe, PercentPipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { ChatPanel } from './components/chat-panel';
import { TracePanel } from './components/trace-panel';
import { TripView } from './components/trip-view';
import { AgentStore } from './core/agent.store';

@Component({
  selector: 'app-root',
  imports: [ChatPanel, TracePanel, TripView, DecimalPipe, PercentPipe],
  template: `
    <div class="aurora" aria-hidden="true"></div>
    <header class="topbar">
      <div class="brand">
        <span class="logo">R</span>
        <div>
          <strong>Rumbo</strong>
          <small>Agente de viajes con IA</small>
        </div>
      </div>

      @if (store.stats(); as s) {
        <div class="kpis">
          <span><b>{{ s.runs }}</b> ejecuciones</span>
          <span><b>{{ s.success_rate === null ? '—' : (s.success_rate | percent) }}</b> éxito</span>
          <span><b>{{ s.avg_iterations }}</b> pasos medios</span>
          <span><b>{{ s.tokens | number }}</b> tokens</span>
        </div>
      }

      @if (store.realAvailable()) {
        <div class="mode-switch" role="group" aria-label="Modo del agente">
          <button
            type="button"
            [class.active]="store.preferredMode() === 'demo'"
            [attr.aria-pressed]="store.preferredMode() === 'demo'"
            [disabled]="store.running()"
            title="Respuestas con reglas, instantáneas y sin coste"
            (click)="store.setMode('demo')"
          >
            Demo
          </button>
          <button
            type="button"
            [class.active]="store.preferredMode() === 'real'"
            [attr.aria-pressed]="store.preferredMode() === 'real'"
            [disabled]="store.running()"
            [title]="'Respuestas con ' + store.modelLabel()"
            (click)="store.setMode('real')"
          >
            {{ store.providerLabel() }}
          </button>
        </div>
      }

      @if (store.health(); as h) {
        @let u = store.usage();
        <span class="mode" [class.demo]="store.isDemo()" [title]="modeHint()">
          @if (!store.isDemo()) {
            <i></i>IA real · {{ store.modelLabel() }}
            @if (u?.remaining; as r) {
              · te quedan {{ r.hour }}
            }
          } @else if (store.preferredMode() === 'demo' && store.realAvailable()) {
            <i></i>Modo demo · sin coste
          } @else if (u && u.mode !== 'demo') {
            <i></i>Modo demo · cupo de IA real agotado
          } @else {
            <i></i>Modo demo · {{ h.model }}
          }
        </span>
      } @else {
        <span class="mode off"><i></i>Backend desconectado</span>
      }
    </header>

    <main class="layout">
      <app-chat-panel />
      <div class="center"><app-trip-view /></div>
      <app-trace-panel />
    </main>
  `,
})
export class App implements OnInit {
  protected readonly store = inject(AgentStore);

  protected modeHint(): string {
    const u = this.store.usage();
    if (this.store.preferredMode() === 'demo' && this.store.realAvailable())
      return 'Has elegido el modo demo: el agente responde con reglas y no gasta cupo de IA real.';
    if (!u || u.mode === 'demo') return 'Sin modelo configurado: el agente funciona con reglas, sin coste.';
    return `Modelo gratuito con límites: ${u.remaining?.hour ?? 0} consultas esta hora y ${u.remaining?.day ?? 0} hoy. Después, modo demo.`;
  }

  ngOnInit(): void {
    this.store.init();
  }
}
