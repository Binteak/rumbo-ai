import { Component, OnInit, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SystemStatusStore } from './core/status/application/system-status.store';
import { TripsStore } from './features/trips/application/trips.store';
import { Topbar } from './layout/topbar/topbar';

/** Raíz de la SPA: la cabecera es fija y cada página se carga en el `router-outlet`. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, Topbar],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly status = inject(SystemStatusStore);
  private readonly trips = inject(TripsStore);

  ngOnInit(): void {
    this.status.init();
    this.trips.load();
  }
}
