import { Observable } from 'rxjs';
import { ChatMode } from '../../../core/status/domain/system-status';
import { AgentEvent } from '../domain/agent-event';

/** Puerto: la conversación con el agente. La aplicación no sabe si detrás hay SSE, WebSocket o un doble. */
export abstract class AgentGateway {
  /** Envía un mensaje y emite cada evento del agente en cuanto ocurre. Cancelar la suscripción lo detiene. */
  abstract send(message: string, sessionId: string | null, mode: ChatMode): Observable<AgentEvent>;
  /** Olvida el historial de la sesión en el servidor. */
  abstract resetSession(sessionId: string): Observable<void>;
}
