import { Injectable, signal } from '@angular/core';

/** Mismo corte que usan las hojas de estilo para la versión móvil. */
export const MOBILE_QUERY = '(max-width: 760px)';

/** Tamaño de la ventana: indica si se está viendo la versión móvil. */
@Injectable({ providedIn: 'root' })
export class Viewport {
  readonly isMobile = signal(false);

  constructor() {
    // Sin `matchMedia` (tests, navegadores antiguos) se asume escritorio.
    if (typeof matchMedia !== 'function') return;
    const query = matchMedia(MOBILE_QUERY);
    this.isMobile.set(query.matches);
    query.addEventListener('change', (event) => this.isMobile.set(event.matches));
  }
}
