import {
  Health,
  Usage,
  answersInDemo,
  currentProvider,
  isRealAvailable,
  resolveMode,
  shortModelName,
} from './system-status';

const demoHealth: Health = { status: 'ok', provider: 'demo', model: 'rumbo-demo' };
const groq: Usage = { provider: 'groq', model: 'openai/gpt-oss-120b', realAi: true };

describe('reglas del estado del servicio', () => {
  it('el uso manda sobre la salud al decidir qué proveedor atiende', () => {
    expect(currentProvider(groq, demoHealth)).toBe('groq');
    expect(currentProvider(null, demoHealth)).toBe('demo');
    expect(currentProvider(null, null)).toBe('');
  });

  it('hay IA real si el proveedor no es el demo', () => {
    expect(isRealAvailable(groq, demoHealth)).toBe(true);
    expect(isRealAvailable(null, demoHealth)).toBe(false);
    expect(isRealAvailable(null, null)).toBe(false);
  });

  it('solo se envía en modo real si está disponible y el usuario lo prefiere', () => {
    expect(resolveMode(true, 'real')).toBe('real');
    expect(resolveMode(true, 'demo')).toBe('demo');
    expect(resolveMode(false, 'real')).toBe('demo');
    expect(resolveMode(true, 'real', true)).toBe('demo');
  });

  it('responde en demo por elección, por cupo agotado o por no haber modelo', () => {
    expect(answersInDemo('demo', groq, demoHealth)).toBe(true);
    expect(answersInDemo('real', { ...groq, realAi: false }, demoHealth)).toBe(true);
    expect(answersInDemo('real', null, demoHealth)).toBe(true);
    expect(answersInDemo('real', groq, demoHealth)).toBe(false);
  });

  it('acorta el nombre del modelo quitando el prefijo del proveedor', () => {
    expect(shortModelName(groq, demoHealth)).toBe('gpt-oss-120b');
    expect(shortModelName(null, demoHealth)).toBe('rumbo-demo');
    expect(shortModelName(null, null)).toBe('');
  });
});
