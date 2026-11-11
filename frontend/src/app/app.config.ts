import { registerLocaleData } from '@angular/common';
import { provideHttpClient, withFetch } from '@angular/common/http';
import localeEs from '@angular/common/locales/es';
import { ApplicationConfig, LOCALE_ID, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { environment } from '../environments/environment';
import { routes } from './app.routes';
import { API_BASE } from './core/config/api-base.token';
import { PreferencesStorage } from './core/status/application/preferences.storage';
import { StatusGateway } from './core/status/application/status.gateway';
import { HttpStatusGateway } from './core/status/infrastructure/http-status.gateway';
import { LocalPreferencesStorage } from './core/status/infrastructure/local-preferences.storage';
import { AgentGateway } from './features/planner/application/agent.gateway';
import { SseAgentGateway } from './features/planner/infrastructure/sse-agent.gateway';
import { TripRepository } from './features/trips/application/trip.repository';
import { HttpTripRepository } from './features/trips/infrastructure/http-trip.repository';

registerLocaleData(localeEs);

/**
 * Raíz de composición: el único sitio que conoce a la vez los puertos y sus adaptadores.
 * Cambiar de HTTP a otra cosa (o a dobles en los tests) es cambiar una línea de aquí.
 */
export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withFetch()),
    provideRouter(routes, withComponentInputBinding()),
    { provide: LOCALE_ID, useValue: 'es' },
    { provide: API_BASE, useValue: environment.apiBase },

    // Puerto → adaptador
    { provide: StatusGateway, useClass: HttpStatusGateway },
    { provide: PreferencesStorage, useClass: LocalPreferencesStorage },
    { provide: TripRepository, useClass: HttpTripRepository },
    { provide: AgentGateway, useClass: SseAgentGateway },
  ],
};
