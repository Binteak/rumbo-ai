import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { API_BASE } from '../../config/api-base.token';
import { StatusGateway } from '../application/status.gateway';
import { GlobalStats, Health, Usage } from '../domain/system-status';
import {
  GlobalStatsDto,
  HealthDto,
  UsageDto,
  toGlobalStats,
  toHealth,
  toUsage,
} from './status.dto';

/** Adaptador HTTP del estado del servicio. */
@Injectable()
export class HttpStatusGateway implements StatusGateway {
  private readonly http = inject(HttpClient);
  private readonly base = inject(API_BASE);

  health(): Observable<Health> {
    return this.http.get<HealthDto>(`${this.base}/health`).pipe(map(toHealth));
  }

  usage(): Observable<Usage> {
    return this.http.get<UsageDto>(`${this.base}/usage`).pipe(map(toUsage));
  }

  stats(): Observable<GlobalStats> {
    return this.http.get<GlobalStatsDto>(`${this.base}/stats`).pipe(map(toGlobalStats));
  }
}
