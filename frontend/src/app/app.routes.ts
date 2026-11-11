import { Routes } from '@angular/router';
import { PlannerPage } from './features/planner/ui/planner-page/planner-page';

/** La portada va en el bundle inicial; el resto de páginas se descargan al entrar en ellas. */
export const routes: Routes = [
  { path: '', pathMatch: 'full', component: PlannerPage, title: 'Rumbo · Agente de viajes con IA' },
  {
    path: 'viajes',
    title: 'Rumbo · Mis viajes',
    loadComponent: () =>
      import('./features/trips/ui/trips-page/trips-page').then((m) => m.TripsPage),
  },
  {
    path: 'viajes/:id',
    title: 'Rumbo · Viaje',
    loadComponent: () =>
      import('./features/trips/ui/trip-detail-page/trip-detail-page').then((m) => m.TripDetailPage),
  },
  { path: '**', redirectTo: '' },
];
