import { bootstrapApplication } from '@angular/platform-browser';
import { polyfillCountryFlagEmojis } from 'country-flag-emoji-polyfill';
import { appConfig } from './app/app.config';
import { App } from './app/app';

// Chrome y Edge en Windows no dibujan los emojis de bandera (salen como "PT", "JP"...).
// Solo en esos navegadores se carga una fuente con las banderas, servida desde la propia web.
polyfillCountryFlagEmojis('Twemoji Country Flags', new URL('fonts/TwemojiCountryFlags.woff2', document.baseURI).href);

bootstrapApplication(App, appConfig)
  .catch((err) => console.error(err));
