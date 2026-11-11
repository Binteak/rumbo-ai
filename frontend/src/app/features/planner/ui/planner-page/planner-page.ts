import { Component, inject } from '@angular/core';
import { TripsStore } from '../../../trips/application/trips.store';
import { TripCard } from '../../../trips/ui/trip-card/trip-card';
import { TripDetail } from '../../../trips/ui/trip-detail/trip-detail';
import { ChatStore } from '../../application/chat.store';
import { ChatPanel } from '../chat-panel/chat-panel';
import { TracePanel } from '../trace-panel/trace-panel';

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
}
