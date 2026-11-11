import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { API_BASE } from '../../../core/config/api-base.token';
import { TripRepository } from '../application/trip.repository';
import { Trip } from '../domain/trip';
import { TripDto, toTrip } from './trip.dto';

/** Adaptador HTTP de los viajes guardados. */
@Injectable()
export class HttpTripRepository implements TripRepository {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE);

  list(): Observable<Trip[]> {
    return this.http.get<TripDto[]>(`${this.base}/trips`).pipe(map((trips) => trips.map(toTrip)));
  }

  getById(id: number): Observable<Trip> {
    return this.http.get<TripDto>(`${this.base}/trips/${id}`).pipe(map(toTrip));
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/trips/${id}`);
  }
}
