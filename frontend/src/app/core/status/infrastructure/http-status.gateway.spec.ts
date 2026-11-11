import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE } from '../../config/api-base.token';
import { GlobalStats, Health, Usage } from '../domain/system-status';
import { HttpStatusGateway } from './http-status.gateway';

describe('HttpStatusGateway', () => {
  let gateway: HttpStatusGateway;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE, useValue: '/api' },
        HttpStatusGateway,
      ],
    });
    gateway = TestBed.inject(HttpStatusGateway);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('GET /api/health y traduce `mode` a proveedor', () => {
    let result: Health | undefined;
    gateway.health().subscribe((h) => (result = h));

    http
      .expectOne({ method: 'GET', url: '/api/health' })
      .flush({ status: 'ok', mode: 'groq', model: 'm' });

    expect(result).toEqual({ status: 'ok', provider: 'groq', model: 'm' });
  });

  it('GET /api/usage y traduce el cupo a camelCase', () => {
    let result: Usage | undefined;
    gateway.usage().subscribe((u) => (result = u));

    http.expectOne({ method: 'GET', url: '/api/usage' }).flush({
      mode: 'gemini',
      model: 'gemini-flash-latest',
      real_ai: true,
      chain: ['gemini', 'groq'],
      remaining: { hour: 4, day: 12 },
      budget_remaining_pct: 80,
    });

    expect(result).toEqual({
      provider: 'gemini',
      model: 'gemini-flash-latest',
      realAi: true,
      chain: ['gemini', 'groq'],
      remaining: { hour: 4, day: 12 },
      budgetRemainingPct: 80,
    });
  });

  it('GET /api/stats y traduce las cifras globales', () => {
    let result: GlobalStats | undefined;
    gateway.stats().subscribe((s) => (result = s));

    http.expectOne({ method: 'GET', url: '/api/stats' }).flush({
      runs: 10,
      success_rate: 0.9,
      avg_duration_ms: 1200,
      avg_iterations: 3.5,
      tool_calls: 40,
      tool_errors: 2,
      tokens: 5000,
      trips: 7,
    });

    expect(result).toEqual({
      runs: 10,
      successRate: 0.9,
      avgDurationMs: 1200,
      avgIterations: 3.5,
      toolCalls: 40,
      toolErrors: 2,
      tokens: 5000,
      trips: 7,
    });
  });
});
