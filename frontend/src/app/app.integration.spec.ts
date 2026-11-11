import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { LOCALE_ID } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter, withComponentInputBinding } from '@angular/router';
import { Observable, Subject, of, throwError } from 'rxjs';
import { App } from './app';
import { routes } from './app.routes';
import { PreferencesStorage } from './core/status/application/preferences.storage';
import { StatusGateway } from './core/status/application/status.gateway';
import { AgentGateway } from './features/planner/application/agent.gateway';
import { AgentEvent } from './features/planner/domain/agent-event';
import { TripRepository } from './features/trips/application/trip.repository';
import { Trip } from './features/trips/domain/trip';
import { aTrip } from './features/trips/testing/trip.fixture';

registerLocaleData(localeEs);

/** Repositorio en memoria: hace de backend de viajes durante el test. */
class InMemoryTrips implements TripRepository {
  trips: Trip[] = [];
  list = (): Observable<Trip[]> => of([...this.trips]);
  getById(id: number): Observable<Trip> {
    const trip = this.trips.find((t) => t.id === id);
    return trip ? of(trip) : throwError(() => new Error('404'));
  }
  delete(id: number): Observable<void> {
    this.trips = this.trips.filter((t) => t.id !== id);
    return of(undefined);
  }
}

/**
 * Test global: arranca la aplicación entera (rutas, stores y componentes reales) y solo
 * sustituye los adaptadores por dobles. Recorre el flujo principal como lo haría un usuario.
 */
describe('Rumbo de principio a fin', () => {
  let fixture: ComponentFixture<App>;
  let el: HTMLElement;
  let router: Router;
  let agent: Subject<AgentEvent>;
  let trips: InMemoryTrips;
  let sent: unknown[][];

  beforeEach(async () => {
    Element.prototype.scrollTo = () => undefined;
    agent = new Subject<AgentEvent>();
    trips = new InMemoryTrips();
    sent = [];

    TestBed.configureTestingModule({
      providers: [
        provideRouter(routes, withComponentInputBinding()),
        { provide: LOCALE_ID, useValue: 'es' },
        { provide: TripRepository, useValue: trips },
        {
          provide: AgentGateway,
          useValue: {
            send: (...args: unknown[]) => {
              sent.push(args);
              return agent;
            },
            resetSession: () => of(undefined),
          },
        },
        {
          provide: StatusGateway,
          useValue: {
            health: () => of({ status: 'ok', provider: 'demo', model: 'rumbo-demo' }),
            usage: () => of({ provider: 'demo', model: 'rumbo-demo', realAi: false }),
            stats: () => of(null),
          },
        },
        {
          provide: PreferencesStorage,
          useValue: { loadMode: () => 'real', saveMode: () => undefined },
        },
      ],
    });

    fixture = TestBed.createComponent(App);
    el = fixture.nativeElement;
    router = TestBed.inject(Router);
    await router.navigateByUrl('/');
    await fixture.whenStable();
  });

  async function write(message: string): Promise<void> {
    const textarea = el.querySelector('textarea')!;
    textarea.value = message;
    textarea.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
  }

  it('planifica un viaje, lo enseña y permite abrirlo desde "Mis viajes"', async () => {
    // 1. Portada vacía.
    expect(el.querySelector('.trip-empty h1')?.textContent).toBe(
      'Planifica un viaje con un agente de IA',
    );
    expect(el.querySelector('.mode')?.textContent).toContain('Modo demo · rumbo-demo');

    // 2. El usuario pide un viaje.
    await write('3 días en Seúl en mayo');
    expect(sent).toEqual([['3 días en Seúl en mayo', null, 'demo']]);
    expect(el.querySelector('.msg.user p')?.textContent).toBe('3 días en Seúl en mayo');
    expect(el.querySelector('.send.stop')).not.toBeNull();

    // 3. El agente trabaja: la traza se va pintando en directo.
    agent.next({
      type: 'run_started',
      runId: 'r1',
      sessionId: 's1',
      provider: 'demo',
      model: 'rumbo-demo',
    });
    agent.next({ type: 'thinking', iteration: 1 });
    agent.next({
      type: 'tool_call',
      id: 't1',
      name: 'get_climate',
      input: { destination_id: 'seul', month: 5 },
    });
    agent.next({
      type: 'tool_result',
      id: 't1',
      name: 'get_climate',
      output: { avg_temp_c: 18 },
      isError: false,
      durationMs: 2,
    });
    await fixture.whenStable();
    expect([...el.querySelectorAll('.step-title span')].map((s) => s.textContent)).toEqual([
      'Razonando · paso 1',
      'Consultar clima',
    ]);
    expect(el.querySelector('.live')).not.toBeNull();

    // 4. Guarda el viaje y responde.
    const trip = aTrip();
    trips.trips = [trip];
    agent.next({ type: 'trip', trip });
    agent.next({ type: 'final', text: 'Te he preparado 3 días en Seúl.' });
    agent.complete();
    await fixture.whenStable();

    expect(el.querySelector('app-trip-detail h1')?.textContent).toBe('3 días en Seúl en mayo');
    expect(el.querySelector('.msg:not(.user) p')?.textContent).toBe(
      'Te he preparado 3 días en Seúl.',
    );
    expect(el.querySelector('.live')).toBeNull();
    expect(el.querySelectorAll('.saved-row app-trip-card').length).toBe(1);

    // 5. Navega a "Mis viajes" sin recargar la página.
    el.querySelector<HTMLAnchorElement>('.nav a[href="/viajes"]')!.click();
    await fixture.whenStable();
    expect(router.url).toBe('/viajes');
    expect(el.querySelector('app-trips-page h1')?.textContent).toBe('Mis viajes');

    // 6. Abre el viaje: tiene URL propia.
    el.querySelector<HTMLButtonElement>('app-trips-page .saved-card')!.click();
    await fixture.whenStable();
    expect(router.url).toBe('/viajes/9');
    expect(el.querySelector('app-trip-detail-page app-trip-detail h1')?.textContent).toBe(
      '3 días en Seúl en mayo',
    );

    // 7. Al volver, la conversación sigue ahí.
    await router.navigateByUrl('/');
    await fixture.whenStable();
    expect(el.querySelectorAll('.msg').length).toBe(2);
  });

  it('abre un viaje directamente por su URL', async () => {
    trips.trips = [aTrip({ id: 31, title: 'Escapada a Lisboa' })];

    await router.navigateByUrl('/viajes/31');
    await fixture.whenStable();

    expect(el.querySelector('app-trip-detail h1')?.textContent).toBe('Escapada a Lisboa');
  });

  it('avisa si el viaje de la URL no existe', async () => {
    await router.navigateByUrl('/viajes/999');
    await fixture.whenStable();

    expect(el.querySelector('.missing h1')?.textContent).toBe('Viaje no encontrado');
  });

  it('una ruta desconocida vuelve al planificador', async () => {
    await router.navigateByUrl('/no-existe');
    await fixture.whenStable();

    expect(router.url).toBe('/');
    expect(el.querySelector('app-planner-page')).not.toBeNull();
  });
});
