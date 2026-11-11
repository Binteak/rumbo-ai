import { Component, effect, inject, signal, untracked } from '@angular/core';
import { TripsStore } from '../../../trips/application/trips.store';
import { TripCard } from '../../../trips/ui/trip-card/trip-card';
import { TripDetail } from '../../../trips/ui/trip-detail/trip-detail';
import { ChatStore } from '../../application/chat.store';
import { ChatPanel } from '../chat-panel/chat-panel';
import { TracePanel } from '../trace-panel/trace-panel';

/** Vista visible en móvil, donde las tres columnas no caben a la vez. */
type PlannerTab = 'chat' | 'trip' | 'trace';

/** Página del planificador. Contenedor: conecta los stores con los componentes presentacionales. */
@Component({
  selector: 'app-planner-page',
  imports: [ChatPanel, TracePanel, TripDetail, TripCard],
  templateUrl: './planner-page.html',
  styleUrl: './planner-page.scss',
})
export class PlannerPage {
  protected readonly chat = inject(ChatStore);
  protected readonly trips = inject(TripsStore);

  protected readonly tab = signal<PlannerTab>('chat');
  /** El agente ha generado un viaje mientras se miraba otra pestaña. */
  protected readonly tripUnseen = signal(false);

  constructor() {
    effect(() => {
      this.trips.selected();
      untracked(() => {
        if (this.chat.running() && this.tab() !== 'trip') this.tripUnseen.set(true);
      });
    });
  }

  protected show(tab: PlannerTab): void {
    this.tab.set(tab);
    if (tab === 'trip') this.tripUnseen.set(false);
  }
}
