import { Observable } from 'rxjs';
import { GlobalStats, Health, Usage } from '../domain/system-status';

/** Puerto: de dónde sale el estado del servicio. La aplicación no sabe que detrás hay HTTP. */
export abstract class StatusGateway {
  abstract health(): Observable<Health>;
  abstract usage(): Observable<Usage>;
  abstract stats(): Observable<GlobalStats>;
}
