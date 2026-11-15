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

/** Destinos con ilustración propia para la cabecera (`public/cities/<id>.svg`). */
const CITY_ART = new Set([
  'lisboa',
  'kioto',
  'reikiavik',
  'cdmx',
  'marrakech',
  'copenhague',
  'seul',
  'buenosaires',
  'ciudaddelcabo',
  'nuevayork',
]);

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

  /** Fondo ilustrado de la cabecera, o `null` si el destino no tiene ilustración. */
  protected readonly art = computed(() => {
    const id = this.trip().destinationId;
    return CITY_ART.has(id) ? `url('cities/${id}.svg')` : null;
  });
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
