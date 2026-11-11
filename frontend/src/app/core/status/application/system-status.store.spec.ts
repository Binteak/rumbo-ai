import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { ChatMode, GlobalStats, Health, Usage } from '../domain/system-status';
import { PreferencesStorage } from './preferences.storage';
import { StatusGateway } from './status.gateway';
import { SystemStatusStore } from './system-status.store';

const health: Health = { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' };
const usage: Usage = {
  provider: 'groq',
  model: 'openai/gpt-oss-120b',
  realAi: true,
  remaining: { hour: 5, day: 15 },
};
const stats = { runs: 4 } as GlobalStats;

/** Doble del puerto de preferencias: memoria en lugar de localStorage. */
class MemoryPreferences implements PreferencesStorage {
  constructor(public mode: ChatMode = 'real') {}
  loadMode = () => this.mode;
  saveMode(mode: ChatMode): void {
    this.mode = mode;
  }
}

function setup(gateway: Partial<StatusGateway>, preferences = new MemoryPreferences()) {
  TestBed.configureTestingModule({
    providers: [
      {
        provide: StatusGateway,
        useValue: {
          health: () => of(health),
          usage: () => of(usage),
          stats: () => of(stats),
          ...gateway,
        },
      },
      { provide: PreferencesStorage, useValue: preferences },
    ],
  });
  return { store: TestBed.inject(SystemStatusStore), preferences };
}

describe('SystemStatusStore', () => {
  it('carga salud, uso y estadísticas al iniciar', () => {
    const { store } = setup({});
    store.init();

    expect(store.health()).toEqual(health);
    expect(store.stats()).toEqual(stats);
    expect(store.realAvailable()).toBe(true);
    expect(store.isDemo()).toBe(false);
    expect(store.modelLabel()).toBe('gpt-oss-120b');
  });

  it('recuerda el modo elegido usando el puerto de preferencias', () => {
    const { store, preferences } = setup({}, new MemoryPreferences('demo'));
    store.init();
    expect(store.preferredMode()).toBe('demo');
    expect(store.effectiveMode()).toBe('demo');

    store.setMode('real');

    expect(preferences.mode).toBe('real');
    expect(store.effectiveMode()).toBe('real');
  });

  it('si el backend no responde queda como desconectado, sin romper', () => {
    const down = () => throwError(() => new Error('sin red'));
    const { store } = setup({ health: down, usage: down, stats: down });
    store.init();

    expect(store.health()).toBeNull();
    expect(store.usage()).toBeNull();
    expect(store.realAvailable()).toBe(false);
    expect(store.effectiveMode()).toBe('demo');
  });
});
