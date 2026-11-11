import { Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { TripsStore } from '../../application/trips.store';
import { Trip } from '../../domain/trip';
import { TripCard } from '../trip-card/trip-card';

/** Página con todos los viajes guardados. Contenedor. */
@Component({
  selector: 'app-trips-page',
  imports: [TripCard, RouterLink],
  templateUrl: './trips-page.html',
  styleUrl: './trips-page.scss',
})
export class TripsPage {
  protected readonly trips = inject(TripsStore);
  private readonly router = inject(Router);

  protected open(trip: Trip): void {
    void this.router.navigate(['/viajes', trip.id]);
  }
}
