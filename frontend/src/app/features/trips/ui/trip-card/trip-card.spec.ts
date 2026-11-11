import { ComponentFixture, TestBed } from '@angular/core/testing';
import { aTrip } from '../../testing/trip.fixture';
import { TripCard } from './trip-card';

describe('TripCard', () => {
  let fixture: ComponentFixture<TripCard>;
  let el: HTMLElement;
  let selected: number;
  let removed: number;

  beforeEach(async () => {
    fixture = TestBed.createComponent(TripCard);
    el = fixture.nativeElement;
    selected = removed = 0;
    fixture.componentInstance.selected.subscribe(() => selected++);
    fixture.componentInstance.removed.subscribe(() => removed++);
    fixture.componentRef.setInput('trip', aTrip());
    await fixture.whenStable();
  });

  it('resume destino, duración y presupuesto', () => {
    expect(el.querySelector('strong')?.textContent).toBe('Seúl');
    expect(el.querySelector('small')?.textContent).toBe('3 días · 800 €');
  });

  it('se marca como activa cuando se lo indican', async () => {
    expect(el.querySelector('.saved-card.active')).toBeNull();

    fixture.componentRef.setInput('active', true);
    await fixture.whenStable();

    expect(el.querySelector('.saved-card.active')).not.toBeNull();
  });

  it('avisa al pulsar la tarjeta', () => {
    el.querySelector<HTMLButtonElement>('.saved-card')!.click();

    expect(selected).toBe(1);
    expect(removed).toBe(0);
  });

  it('borrar no selecciona la tarjeta', () => {
    el.querySelector<HTMLElement>('.del')!.click();

    expect(removed).toBe(1);
    expect(selected).toBe(0);
  });
});
