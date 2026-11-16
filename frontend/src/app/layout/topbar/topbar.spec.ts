import { registerLocaleData } from '@angular/common';
import localeEs from '@angular/common/locales/es';
import { LOCALE_ID, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { PreferencesStorage } from '../../core/status/application/preferences.storage';
import { StatusGateway } from '../../core/status/application/status.gateway';
import { SystemStatusStore } from '../../core/status/application/system-status.store';
import { GlobalStats, Health, Usage } from '../../core/status/domain/system-status';
import { Viewport } from '../../core/viewport/viewport';
import { AgentGateway } from '../../features/planner/application/agent.gateway';
import { TripRepository } from '../../features/trips/application/trip.repository';
import { providerLabel } from './provider-label';
import { Topbar } from './topbar';

registerLocaleData(localeEs);

const stats: GlobalStats = {
  runs: 12,
  successRate: 0.75,
  avgDurationMs: 900,
  avgIterations: 3.2,
  toolCalls: 30,
  toolErrors: 1,
  tokens: 15000,
  trips: 4,
};

describe('Topbar', () => {
  let fixture: ComponentFixture<Topbar>;
  let el: HTMLElement;
  let saved: string[];

  async function render(health: Health | null, usage: Usage | null, mobile = false): Promise<void> {
    saved = [];
    const down = () => throwError(() => new Error('sin red'));
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: LOCALE_ID, useValue: 'es' },
        {
          provide: StatusGateway,
          useValue: {
            health: health ? () => of(health) : down,
            usage: usage ? () => of(usage) : down,
            stats: () => of(stats),
          },
        },
        {
          provide: PreferencesStorage,
          useValue: { loadMode: () => 'real', saveMode: (m: string) => saved.push(m) },
        },
        { provide: Viewport, useValue: { isMobile: signal(mobile) } },
        { provide: AgentGateway, useValue: {} },
        { provide: TripRepository, useValue: {} },
      ],
    });
    TestBed.inject(SystemStatusStore).init();
    fixture = TestBed.createComponent(Topbar);
    el = fixture.nativeElement;
    await fixture.whenStable();
  }

  const mode = () => el.querySelector('.mode')?.textContent?.replace(/\s+/g, ' ').trim();
  const openPanel = async () => {
    el.querySelector<HTMLButtonElement>('button.mode')!.click();
    await fixture.whenStable();
    return el.querySelector('.model-panel')!;
  };
  const rows = () =>
    [...el.querySelectorAll('.chain li')].map((li) => [
      li.className,
      li.querySelector('.name')?.textContent?.trim(),
      li.querySelector('small')?.textContent?.trim(),
    ]);

  const chainUsage: Usage = {
    provider: 'gemini',
    model: 'gemini-3.5-flash-lite',
    realAi: true,
    remaining: { hour: 4, day: 12 },
    providers: [
      {
        name: 'gemini',
        label: 'Gemini',
        model: 'gemini-3.5-flash-lite',
        status: 'active',
        callsToday: 23,
        dailyLimit: 500,
      },
      {
        name: 'groq',
        label: 'Groq',
        model: 'openai/gpt-oss-120b',
        status: 'paused',
        pausedSeconds: 720,
        callsToday: 1000,
        dailyLimit: 1000,
      },
      {
        name: 'deepseek',
        label: 'DeepSeek',
        model: 'deepseek/deepseek-v4-flash:free',
        status: 'standby',
        callsToday: 1,
        dailyLimit: null,
      },
      { name: 'demo', label: 'Modo demo', model: 'rumbo-demo', status: 'standby' },
    ],
  };

  it('da nombre legible a los proveedores', () => {
    expect(providerLabel('huggingface')).toBe('Hugging Face');
    expect(providerLabel('mistral')).toBe('Mistral');
    expect(providerLabel('')).toBe('IA real');
  });

  it('enlaza las secciones', async () => {
    await render({ status: 'ok', provider: 'demo', model: 'rumbo-demo' }, null);

    const links = [...el.querySelectorAll<HTMLAnchorElement>('.nav a')].map((a) => [
      a.textContent,
      a.getAttribute('href'),
    ]);
    expect(links).toEqual([
      ['Planificador', '/'],
      ['Mis viajes', '/viajes'],
    ]);
  });

  it('muestra el modelo que responde con su nombre de producto, sin selector de modo', async () => {
    await render({ status: 'ok', provider: 'gemini', model: 'gemini-3.5-flash-lite' }, chainUsage);

    expect(mode()).toBe('Gemini 3.5 Flash-Lite');
    expect(el.querySelector('.mode.demo')).toBeNull();
    expect(el.querySelector('.mode-switch')).toBeNull();
  });

  it('añade quién sirve el modelo si el nombre no lo dice', async () => {
    await render(
      { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' },
      { provider: 'groq', model: 'openai/gpt-oss-120b', realAi: true },
    );

    expect(mode()).toBe('GPT-OSS 120B · Groq');
  });

  it('el panel enseña toda la cadena con la cuota de cada modelo, tus consultas y las cifras', async () => {
    await render({ status: 'ok', provider: 'gemini', model: 'gemini-3.5-flash-lite' }, chainUsage);
    const panel = await openPanel();

    expect(rows()).toEqual([
      ['active', 'Gemini 3.5 Flash-Lite', '≈ 477 de 500 llamadas hoy'],
      ['paused', 'GPT-OSS 120B · Groq', 'En pausa · vuelve en 12 min'],
      ['standby', 'DeepSeek V4 Flash', '1 llamada hoy'],
      ['standby', 'Modo demo', 'Sin límite · respuestas con reglas'],
    ]);
    expect(panel.querySelector('.chain li.active .tag')?.textContent).toBe('En uso');
    expect(panel.querySelector('.mine')?.textContent?.replace(/\s+/g, ' ')).toContain(
      'quedan 4 esta hora y 12 hoy',
    );
    // El formato español separa el porcentaje con un espacio no separable.
    const kpis = [...panel.querySelectorAll('.kpis dd')].map((d) =>
      d.textContent?.replace(/\s/g, ' '),
    );
    expect(kpis).toEqual(['12', '75 %', '3.2', '15.000']);
  });

  it('desde el panel se puede probar el modo demo y volver, y se recuerda', async () => {
    await render({ status: 'ok', provider: 'gemini', model: 'gemini-3.5-flash-lite' }, chainUsage);
    await openPanel();

    el.querySelector<HTMLButtonElement>('.switch')!.click();
    await fixture.whenStable();

    expect(saved).toEqual(['demo']);
    expect(mode()).toBe('Modo demo');
    expect(rows().map((r) => r[0])).toEqual(['standby', 'paused', 'standby', 'active']);
    expect(el.querySelector('.switch')?.textContent?.trim()).toBe('Volver a la IA real');
  });

  it('avisa cuando se ha agotado el cupo de IA real', async () => {
    await render(
      { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' },
      {
        provider: 'groq',
        model: 'openai/gpt-oss-120b',
        realAi: false,
        remaining: { hour: 0, day: 3 },
      },
    );

    expect(mode()).toBe('Modo demo · cupo agotado');
    expect(el.querySelector('.mode.demo')).not.toBeNull();
  });

  it('sin modelo configurado muestra el modo demo y no ofrece cambiar', async () => {
    await render(
      { status: 'ok', provider: 'demo', model: 'rumbo-demo' },
      {
        provider: 'demo',
        model: 'rumbo-demo',
        realAi: false,
        providers: [{ name: 'demo', label: 'Modo demo', model: 'rumbo-demo', status: 'active' }],
      },
    );

    expect(mode()).toBe('Modo demo');
    await openPanel();
    expect(rows()).toEqual([['active', 'Modo demo', 'Sin límite · respuestas con reglas']]);
    expect(el.querySelector('.switch')).toBeNull();
  });

  it('en el móvil responde el modo demo aunque haya IA real', async () => {
    await render(
      { status: 'ok', provider: 'gemini', model: 'gemini-3.5-flash-lite' },
      chainUsage,
      true,
    );

    expect(mode()).toBe('Modo demo');
    expect(TestBed.inject(SystemStatusStore).effectiveMode()).toBe('demo');
    const panel = await openPanel();
    expect(panel.querySelector('.note')?.textContent).toContain('En el móvil');
    expect(el.querySelector('.switch')).toBeNull();
  });

  it('el botón de información explica que el backend se duerme y se cierra al pulsar fuera', async () => {
    await render({ status: 'ok', provider: 'demo', model: 'rumbo-demo' }, null);
    expect(el.querySelector('.info-panel')).toBeNull();

    el.querySelector<HTMLButtonElement>('.info-btn')!.click();
    await fixture.whenStable();

    const panel = el.querySelector('.info-panel')!;
    expect(panel.textContent).toContain('refresca la página');
    expect(panel.textContent).toContain('19:00');
    expect(panel.querySelector('.info-reload')).not.toBeNull();

    document.body.click();
    await fixture.whenStable();
    expect(el.querySelector('.info-panel')).toBeNull();
  });

  it('indica que el backend no responde', async () => {
    await render(null, null);

    expect(mode()).toBe('Backend desconectado');
    expect(el.querySelector('.mode.off')).not.toBeNull();
  });
});
