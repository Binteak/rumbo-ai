import { InjectionToken } from '@angular/core';

/** URL base de la API ("/api" tras el proxy, o la URL completa del backend en Render). */
export const API_BASE = new InjectionToken<string>('API_BASE');
