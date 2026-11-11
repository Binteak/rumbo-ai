import { Injectable } from '@angular/core';
import { PreferencesStorage } from '../application/preferences.storage';
import { ChatMode } from '../domain/system-status';

const MODE_KEY = 'rumbo.mode';

/** Adaptador de preferencias sobre `localStorage`. Si el navegador lo bloquea, no falla. */
@Injectable()
export class LocalPreferencesStorage implements PreferencesStorage {
  loadMode(): ChatMode {
    try {
      return localStorage.getItem(MODE_KEY) === 'demo' ? 'demo' : 'real';
    } catch {
      return 'real';
    }
  }

  saveMode(mode: ChatMode): void {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* sin almacenamiento disponible: la elección dura lo que la pestaña */
    }
  }
}
