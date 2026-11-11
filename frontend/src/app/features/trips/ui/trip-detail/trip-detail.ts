import { DecimalPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { Trip, budgetBreakdown, dayCost, dayHours } from '../../domain/trip';

const MONTHS = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

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
const DEFAULT_HUE: [string, string] = ['#2dd4bf', '#8b5cf6'];

const BUDGET_LABELS: Record<string, string> = {
  alojamiento: 'Alojamiento',
  comida: 'Comida',
  transporte_local: 'Transporte local',
  actividades: 'Actividades',
};

/** Ficha completa de un viaje: cabecera, presupuesto, clima e itinerario. Presentacional. */
@Component({
  selector: 'app-trip-detail',
  imports: [DecimalPipe],
  templateUrl: './trip-detail.html',
  styleUrl: './trip-detail.scss',
})
export class TripDetail {
  readonly trip = input.required<Trip>();

  protected readonly hue = computed(() => HUES[this.trip().destinationId] ?? DEFAULT_HUE);
  protected readonly monthName = computed(() => {
    const month = this.trip().month;
    return month ? MONTHS[month - 1] : null;
  });
  protected readonly budgetRows = computed(() =>
    budgetBreakdown(this.trip().budget).map((line) => ({
      ...line,
      label: BUDGET_LABELS[line.key] ?? line.key,
    })),
  );

  protected readonly dayHours = dayHours;
  protected readonly dayCost = dayCost;
}
