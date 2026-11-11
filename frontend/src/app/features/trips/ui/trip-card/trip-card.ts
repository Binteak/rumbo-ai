import { DecimalPipe } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { Trip } from '../../domain/trip';

/** Tarjeta resumen de un viaje guardado. Presentacional: avisa al padre de la selección y del borrado. */
@Component({
  selector: 'app-trip-card',
  imports: [DecimalPipe],
  templateUrl: './trip-card.html',
  styleUrl: './trip-card.scss',
})
export class TripCard {
  readonly trip = input.required<Trip>();
  readonly active = input(false);

  readonly selected = output<void>();
  readonly removed = output<void>();

  protected remove(event: Event): void {
    // El aspa está dentro de la tarjeta: sin esto, borrar también la seleccionaría.
    event.stopPropagation();
    this.removed.emit();
  }
}
