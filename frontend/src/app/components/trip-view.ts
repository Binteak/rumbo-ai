import { DecimalPipe } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { AgentStore } from '../core/agent.store';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

/** Paleta por destino para el fondo de la cabecera. */
const HUES: Record<string, [string, string]> = {
  lisboa: ['#f59e0b', '#ef4444'],
  kioto: ['#f472b6', '#7c3aed'],
  reikiavik: ['#22d3ee', '#4f46e5'],
  cdmx: ['#fb7185', '#f59e0b'],
  marrakech: ['#f97316', '#be123c'],
  copenhague: ['#38bdf8', '#0f766e'],
  seul: ['#a78bfa', '#ec4899'],
  buenosaires: ['#60a5fa', '#f472b6'],
  ciudaddelcabo: ['#34d399', '#0ea5e9'],
  nuevayork: ['#facc15', '#6366f1'],
};

const BUDGET_LABELS: Record<string, string> = {
  alojamiento: 'Alojamiento',
  comida: 'Comida',
  transporte_local: 'Transporte local',
  actividades: 'Actividades',
};

@Component({
  selector: 'app-trip-view',
  imports: [DecimalPipe],
  template: `
    @if (trip(); as t) {
      <section class="trip">
        <header class="hero" [style.--h1]="hue()[0]" [style.--h2]="hue()[1]">
          <div class="hero-glow"></div>
          <span class="flag">{{ t.flag }}</span>
          <div>
            <p class="eyebrow">Viaje guardado · #{{ t.id }}</p>
            <h1>{{ t.title }}</h1>
            <p class="summary">{{ t.summary }}</p>
            <div class="chips">
              <span>{{ t.days }} días</span>
              <span>{{ t.travelers }} {{ t.travelers === 1 ? 'viajero' : 'viajeros' }}</span>
              <span class="cap">{{ t.style }}</span>
              @if (t.month) {
                <span class="cap">{{ month(t.month) }}</span>
              }
            </div>
          </div>
        </header>

        <div class="cards">
          <article class="card budget">
            <p class="eyebrow">Presupuesto estimado</p>
            <p class="big">{{ t.budget.total_eur | number }} €</p>
            <p class="muted">{{ t.budget.total_per_person_eur | number }} € por persona · sin vuelos</p>
            <ul class="bars">
              @for (row of budgetRows(); track row.key) {
                <li>
                  <span>{{ row.label }}</span>
                  <div class="bar"><i [style.width.%]="row.pct"></i></div>
                  <strong>{{ row.value | number }} €</strong>
                </li>
              }
            </ul>
          </article>

          <article class="card climate">
            <p class="eyebrow">Clima</p>
            @if (t.climate; as c) {
              <p class="big">{{ c.avg_temp_c }}°<small>C</small></p>
              <p class="muted">Media en {{ c.month }} · {{ c.rain_days }} días de lluvia</p>
              <p class="verdict">{{ c.verdict }}</p>
            } @else {
              <p class="muted">Indica el mes del viaje para ver el clima.</p>
            }
          </article>
        </div>

        <div class="days">
          @for (day of t.itinerary; track day.day) {
            <article class="day" [style.animation-delay.ms]="day.day * 70">
              <header>
                <span class="day-n">Día {{ day.day }}</span>
                <small>{{ dayHours(day.activities) }} h · {{ dayCost(day.activities) }} €</small>
              </header>
              @for (a of day.activities; track a.name) {
                <div class="act">
                  <span class="slot">{{ a.slot }}</span>
                  <p>{{ a.name }}</p>
                  <div class="meta">
                    <span class="tag" [attr.data-cat]="a.category">{{ a.category }}</span>
                    <span>{{ a.area }}</span>
                    <span>{{ a.price_eur ? a.price_eur + ' €' : 'Gratis' }}</span>
                  </div>
                </div>
              }
            </article>
          }
        </div>
      </section>
    } @else {
      <section class="trip-empty">
        <div class="orb"></div>
        <h1>Planifica un viaje con un agente de IA</h1>
        <p>
          Rumbo razona, elige herramientas (destinos, clima, presupuesto, itinerario) y guarda el resultado. Pídeselo en el chat y
          observa la traza en la derecha.
        </p>
      </section>
    }

    @if (store.trips().length) {
      <section class="saved">
        <p class="eyebrow">Mis viajes</p>
        <div class="saved-row">
          @for (t of store.trips(); track t.id) {
            <button class="saved-card" [class.active]="t.id === trip()?.id" (click)="store.selectedTrip.set(t)">
              <span>{{ t.flag }}</span>
              <strong>{{ t.destination_name }}</strong>
              <small>{{ t.days }} días · {{ t.budget.total_eur | number }} €</small>
              <i class="del" role="button" aria-label="Eliminar" (click)="$event.stopPropagation(); store.removeTrip(t)">×</i>
            </button>
          }
        </div>
      </section>
    }
  `,
})
export class TripView {
  protected readonly store = inject(AgentStore);
  protected readonly trip = this.store.selectedTrip;
  protected readonly hue = computed(() => HUES[this.trip()?.destination_id ?? ''] ?? ['#2dd4bf', '#8b5cf6']);

  protected readonly budgetRows = computed(() => {
    const b = this.trip()?.budget;
    if (!b) return [];
    const max = Math.max(...Object.values(b.per_person));
    return Object.entries(b.per_person).map(([key, v]) => ({
      key,
      label: BUDGET_LABELS[key] ?? key,
      value: v * b.travelers,
      pct: (v / max) * 100,
    }));
  });

  protected month(m: number): string {
    return MONTHS[m - 1];
  }

  protected dayHours(acts: { duration_h: number }[]): number {
    return acts.reduce((s, a) => s + a.duration_h, 0);
  }

  protected dayCost(acts: { price_eur: number }[]): number {
    return acts.reduce((s, a) => s + a.price_eur, 0);
  }
}
