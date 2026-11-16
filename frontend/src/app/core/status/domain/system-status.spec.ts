import {
  Health,
  Usage,
  answersInDemo,
  currentProvider,
  isRealAvailable,
  formatWait,
  prettyModelName,
  quotaText,
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

  it('da a cada modelo su nombre de producto', () => {
    expect(prettyModelName('gemini-3.5-flash-lite')).toBe('Gemini 3.5 Flash-Lite');
    expect(prettyModelName('openai/gpt-oss-120b')).toBe('GPT-OSS 120B');
    expect(prettyModelName('deepseek/deepseek-v4-flash:free')).toBe('DeepSeek V4 Flash');
    expect(prettyModelName('claude-sonnet-5-5')).toBe('Claude Sonnet 5.5');
    expect(prettyModelName('gemini-flash-latest')).toBe('Gemini Flash (última)');
    expect(prettyModelName('rumbo-demo')).toBe('Modo demo');
  });

  it('describe la cuota que le queda a cada modelo', () => {
    const base = { name: 'groq', label: 'Groq', model: 'openai/gpt-oss-120b' };
    expect(quotaText({ ...base, status: 'active', callsToday: 1200, dailyLimit: 1000 })).toBe(
      '≈ 0 de 1000 llamadas hoy',
    );
    expect(quotaText({ ...base, status: 'standby', callsToday: 0 })).toBe('0 llamadas hoy');
    expect(quotaText({ ...base, status: 'paused', pausedSeconds: 30 })).toBe(
      'En pausa · vuelve en 1 min',
    );
    expect(formatWait(3600)).toBe('1 h');
    expect(formatWait(5400)).toBe('1 h 30 min');
  });
});
