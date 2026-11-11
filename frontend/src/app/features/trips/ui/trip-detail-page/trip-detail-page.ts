import { Component, effect, inject, input, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TripsStore } from '../../application/trips.store';
import { TripDetail } from '../trip-detail/trip-detail';

/** Página de un viaje con URL propia (`/viajes/:id`). Contenedor. */
@Component({
  selector: 'app-trip-detail-page',
  imports: [TripDetail, RouterLink],
  templateUrl: './trip-detail-page.html',
  styleUrl: './trip-detail-page.scss',
})
export class TripDetailPage {
  /** Parámetro de la ruta: el router lo enlaza a este input. */
  readonly id = input.required<string>();

  protected readonly trips = inject(TripsStore);

  constructor() {
    effect(() => {
      const id = Number(this.id());
      untracked(() => this.trips.open(id));
    });
  }
}
