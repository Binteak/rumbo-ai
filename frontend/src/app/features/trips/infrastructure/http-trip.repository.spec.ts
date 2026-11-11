import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE } from '../../../core/config/api-base.token';
import { Trip } from '../domain/trip';
import { aTrip, aTripDto } from '../testing/trip.fixture';
import { HttpTripRepository } from './http-trip.repository';
import { toTrip } from './trip.dto';

describe('HttpTripRepository', () => {
  let repository: HttpTripRepository;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE, useValue: '/api' },
        HttpTripRepository,
      ],
    });
    repository = TestBed.inject(HttpTripRepository);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('traduce el viaje de la API (snake_case) al modelo de dominio', () => {
    expect(toTrip(aTripDto())).toEqual(aTrip());
    expect(toTrip(aTripDto({ climate: null, month: null })).climate).toBeNull();
  });

  it('GET /api/trips devuelve los viajes ya traducidos', () => {
    let result: Trip[] | undefined;
    repository.list().subscribe((trips) => (result = trips));

    http.expectOne({ method: 'GET', url: '/api/trips' }).flush([aTripDto()]);

    expect(result).toEqual([aTrip()]);
  });

  it('GET /api/trips/:id devuelve un viaje', () => {
    let result: Trip | undefined;
    repository.getById(9).subscribe((trip) => (result = trip));

    http.expectOne({ method: 'GET', url: '/api/trips/9' }).flush(aTripDto());

    expect(result?.destinationName).toBe('Seúl');
  });

  it('DELETE /api/trips/:id elimina un viaje', () => {
    let done = false;
    repository.delete(9).subscribe(() => (done = true));

    http
      .expectOne({ method: 'DELETE', url: '/api/trips/9' })
      .flush(null, { status: 204, statusText: 'No Content' });

    expect(done).toBe(true);
  });
});
