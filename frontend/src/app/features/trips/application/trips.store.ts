import { Injectable, inject, signal } from '@angular/core';
import { Subscription } from 'rxjs';
import { Trip } from '../domain/trip';
import { TripRepository } from './trip.repository';

export type DetailStatus = 'idle' | 'loading' | 'ready' | 'missing';

/** Viajes guardados: la lista, el que se muestra en el planificador y el que se abre por URL. */
@Injectable({ providedIn: 'root' })
export class TripsStore {
  private readonly repository = inject(TripRepository);
  private detailRequest?: Subscription;

  readonly trips = signal<Trip[]>([]);
  /** Viaje visible en el planificador. */
  readonly selected = signal<Trip | null>(null);
  /** Viaje abierto en su propia página (`/viajes/:id`). */
  readonly detail = signal<Trip | null>(null);
  readonly detailStatus = signal<DetailStatus>('idle');

  load(): void {
    this.repository.list().subscribe((trips) => {
      this.trips.set(trips);
      if (!this.selected() && trips.length) this.selected.set(trips[0]);
    });
  }

  select(trip: Trip): void {
    this.selected.set(trip);
  }

  remove(trip: Trip): void {
    this.repository.delete(trip.id).subscribe(() => {
      if (this.selected()?.id === trip.id) this.selected.set(null);
      this.load();
    });
  }

  /** Abre un viaje por id: usa la lista si ya está cargada y, si no, lo pide al servidor. */
  open(id: number): void {
    this.detailRequest?.unsubscribe();
    const cached = this.trips().find((trip) => trip.id === id);
    if (cached) {
      this.detail.set(cached);
      this.detailStatus.set('ready');
      return;
    }
    this.detail.set(null);
    this.detailStatus.set('loading');
    this.detailRequest = this.repository.getById(id).subscribe({
      next: (trip) => {
        this.detail.set(trip);
        this.detailStatus.set('ready');
      },
      error: () => this.detailStatus.set('missing'),
    });
  }
}
