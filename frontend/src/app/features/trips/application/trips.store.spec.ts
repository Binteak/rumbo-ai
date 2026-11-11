import { TestBed } from '@angular/core/testing';
import { Observable, of, throwError } from 'rxjs';
import { Trip } from '../domain/trip';
import { aTrip } from '../testing/trip.fixture';
import { TripRepository } from './trip.repository';
import { TripsStore } from './trips.store';

/** Doble del puerto: un repositorio en memoria. */
class InMemoryTripRepository implements TripRepository {
  constructor(public trips: Trip[]) {}

  list(): Observable<Trip[]> {
    return of([...this.trips]);
  }

  getById(id: number): Observable<Trip> {
    const trip = this.trips.find((t) => t.id === id);
    return trip ? of(trip) : throwError(() => new Error('404'));
  }

  delete(id: number): Observable<void> {
    this.trips = this.trips.filter((t) => t.id !== id);
    return of(undefined);
  }
}

function setup(trips: Trip[]) {
  const repository = new InMemoryTripRepository(trips);
  TestBed.configureTestingModule({
    providers: [{ provide: TripRepository, useValue: repository }],
  });
  return { store: TestBed.inject(TripsStore), repository };
}

describe('TripsStore', () => {
  const seul = aTrip({ id: 9 });
  const lisboa = aTrip({ id: 4, destinationId: 'lisboa', destinationName: 'Lisboa' });

  it('al cargar muestra el viaje más reciente si no había ninguno elegido', () => {
    const { store } = setup([seul, lisboa]);
    store.load();

    expect(store.trips()).toEqual([seul, lisboa]);
    expect(store.selected()).toEqual(seul);
  });

  it('recargar no cambia el viaje que el usuario había elegido', () => {
    const { store } = setup([seul, lisboa]);
    store.load();
    store.select(lisboa);

    store.load();

    expect(store.selected()).toEqual(lisboa);
  });

  it('al borrar el viaje visible pasa a mostrar el siguiente', () => {
    const { store } = setup([seul, lisboa]);
    store.load();

    store.remove(seul);

    expect(store.trips()).toEqual([lisboa]);
    expect(store.selected()).toEqual(lisboa);
  });

  it('abre un viaje de la lista sin volver a pedirlo', () => {
    const { store, repository } = setup([seul]);
    const getById = vi.spyOn(repository, 'getById');
    store.load();

    store.open(9);

    expect(store.detailStatus()).toBe('ready');
    expect(store.detail()).toEqual(seul);
    expect(getById).not.toHaveBeenCalled();
  });

  it('abre por URL un viaje que no está en la lista pidiéndolo al repositorio', () => {
    const { store } = setup([seul]);

    store.open(9);

    expect(store.detailStatus()).toBe('ready');
    expect(store.detail()).toEqual(seul);
  });

  it('marca como no encontrado un viaje que no existe', () => {
    const { store } = setup([]);

    store.open(404);

    expect(store.detailStatus()).toBe('missing');
    expect(store.detail()).toBeNull();
  });
});
