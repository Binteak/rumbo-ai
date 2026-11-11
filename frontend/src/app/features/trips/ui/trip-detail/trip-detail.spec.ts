import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Trip } from '../../domain/trip';
import { aTrip } from '../../testing/trip.fixture';
import { TripDetail } from './trip-detail';

describe('TripDetail', () => {
  let fixture: ComponentFixture<TripDetail>;
  let el: HTMLElement;

  async function render(trip: Trip): Promise<void> {
    fixture.componentRef.setInput('trip', trip);
    await fixture.whenStable();
  }

  beforeEach(() => {
    fixture = TestBed.createComponent(TripDetail);
    el = fixture.nativeElement;
  });

  it('muestra la cabecera con los datos del viaje', async () => {
    await render(aTrip());

    expect(el.querySelector('h1')?.textContent).toBe('3 días en Seúl en mayo');
    expect(el.querySelector('.hero .eyebrow')?.textContent).toBe('Viaje guardado · #9');
    const chips = [...el.querySelectorAll('.chips span')].map((c) => c.textContent?.trim());
    expect(chips).toEqual(['3 días', '2 viajeros', 'confort', 'mayo']);
  });

  it('usa el singular con un solo viajero y omite el mes si no se conoce', async () => {
    await render(aTrip({ travelers: 1, month: null, climate: null }));

    const chips = [...el.querySelectorAll('.chips span')].map((c) => c.textContent?.trim());
    expect(chips).toEqual(['3 días', '1 viajero', 'confort']);
    expect(el.querySelector('.climate .muted')?.textContent).toBe(
      'Indica el mes del viaje para ver el clima.',
    );
  });

  it('desglosa el presupuesto para todo el grupo con etiquetas legibles', async () => {
    await render(aTrip());

    const rows = [...el.querySelectorAll('.bars li')].map((li) => [
      li.querySelector('span')?.textContent,
      li.querySelector('strong')?.textContent,
    ]);
    expect(rows).toEqual([
      ['Alojamiento', '360 €'],
      ['Comida', '240 €'],
      ['Transporte local', '80 €'],
      ['Actividades', '120 €'],
    ]);
    expect(el.querySelector<HTMLElement>('.bar i')?.style.width).toBe('100%');
  });

  it('resume horas y coste de cada día y marca lo gratuito', async () => {
    const trip = aTrip();
    trip.itinerary[0].activities[0].priceEur = 0;
    await render(trip);

    expect(el.querySelector('.day header small')?.textContent).toBe('5.5 h · 25 €');
    const prices = [...el.querySelectorAll('.act .meta span:last-child')].map((s) => s.textContent);
    expect(prices).toEqual(['Gratis', '25 €']);
  });

  it('usa una paleta por defecto para un destino sin colores propios', async () => {
    await render(aTrip({ destinationId: 'atlantida' }));

    expect(el.querySelector<HTMLElement>('.hero')?.style.getPropertyValue('--h1')).toBe('#2dd4bf');
  });
});
