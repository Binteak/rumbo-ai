import { Observable } from 'rxjs';
import { Trip } from '../domain/trip';

/** Puerto: acceso a los viajes guardados. */
export abstract class TripRepository {
  abstract list(): Observable<Trip[]>;
  abstract getById(id: number): Observable<Trip>;
  abstract delete(id: number): Observable<void>;
}
