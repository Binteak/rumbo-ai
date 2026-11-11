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

  it('da nombre legible a los proveedores', () => {
    expect(providerLabel('huggingface')).toBe('Hugging Face');
    expect(providerLabel('mistral')).toBe('Mistral');
    expect(providerLabel('')).toBe('IA real');
  });

  it('enlaza las secciones y muestra las cifras globales', async () => {
    await render({ status: 'ok', provider: 'demo', model: 'rumbo-demo' }, null);

    const links = [...el.querySelectorAll<HTMLAnchorElement>('.nav a')].map((a) => [
      a.textContent,
      a.getAttribute('href'),
    ]);
    expect(links).toEqual([
      ['Planificador', '/'],
      ['Mis viajes', '/viajes'],
    ]);
    // El formato español separa el porcentaje con un espacio no separable.
    const kpis = [...el.querySelectorAll('.kpis b')].map((b) => b.textContent?.replace(/\s/g, ' '));
    expect(kpis).toEqual(['12', '75 %', '3.2', '15.000']);
  });

  it('con IA real indica el modelo y las consultas que quedan', async () => {
    await render(
      { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' },
      {
        provider: 'groq',
        model: 'openai/gpt-oss-120b',
        realAi: true,
        remaining: { hour: 4, day: 12 },
      },
    );

    expect(mode()).toBe('IA real · gpt-oss-120b · te quedan 4');
    expect(el.querySelector('.mode')?.getAttribute('title')).toContain(
      '4 consultas esta hora y 12 hoy',
    );
    expect(el.querySelector('.mode-switch button.active')?.textContent?.trim()).toBe('Groq');
  });

  it('permite pasar al modo demo y lo recuerda', async () => {
    await render(
      { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' },
      { provider: 'groq', model: 'openai/gpt-oss-120b', realAi: true },
    );

    el.querySelector<HTMLButtonElement>('.mode-switch button')!.click();
    await fixture.whenStable();

    expect(saved).toEqual(['demo']);
    expect(mode()).toBe('Modo demo · sin coste');
    expect(el.querySelector('.mode.demo')).not.toBeNull();
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

    expect(mode()).toBe('Modo demo · cupo de IA real agotado');
  });

  it('sin modelo configurado no ofrece el selector de modo', async () => {
    await render(
      { status: 'ok', provider: 'demo', model: 'rumbo-demo' },
      { provider: 'demo', model: 'rumbo-demo', realAi: false },
    );

    expect(el.querySelector('.mode-switch')).toBeNull();
    expect(mode()).toBe('Modo demo · rumbo-demo');
  });

  it('en el móvil solo ofrece el modo demo aunque haya IA real', async () => {
    await render(
      { status: 'ok', provider: 'groq', model: 'openai/gpt-oss-120b' },
      { provider: 'groq', model: 'openai/gpt-oss-120b', realAi: true, remaining: { hour: 4, day: 12 } },
      true,
    );

    expect(el.querySelector('.mode-switch')).toBeNull();
    expect(mode()).toBe('Modo demo · sin coste');
    expect(TestBed.inject(SystemStatusStore).effectiveMode()).toBe('demo');
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
