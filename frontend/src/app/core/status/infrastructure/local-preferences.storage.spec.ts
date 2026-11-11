import { LocalPreferencesStorage } from './local-preferences.storage';

describe('LocalPreferencesStorage', () => {
  const storage = new LocalPreferencesStorage();

  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('por defecto el modo es el real', () => {
    expect(storage.loadMode()).toBe('real');
  });

  it('guarda y recupera el modo con la clave de siempre', () => {
    storage.saveMode('demo');

    expect(localStorage.getItem('rumbo.mode')).toBe('demo');
    expect(storage.loadMode()).toBe('demo');
  });

  it('si el navegador bloquea el almacenamiento, no falla', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqueado');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqueado');
    });

    expect(storage.loadMode()).toBe('real');
    expect(() => storage.saveMode('demo')).not.toThrow();
  });
});
