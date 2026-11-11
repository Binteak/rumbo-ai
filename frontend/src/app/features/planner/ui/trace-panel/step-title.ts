import { TraceStep } from '../../domain/run';

/** Nombre legible de cada herramienta del agente. */
export const TOOL_LABELS: Record<string, string> = {
  search_destinations: 'Buscar destinos',
  get_climate: 'Consultar clima',
  estimate_budget: 'Calcular presupuesto',
  build_itinerary: 'Crear itinerario',
  search_travel_guides: 'Buscar en las guías (RAG)',
  save_trip: 'Guardar viaje',
};

/** Título de un paso de la traza. El dominio guarda datos; el texto se decide aquí. */
export function stepTitle(step: TraceStep): string {
  switch (step.kind) {
    case 'thinking':
      return `Razonando · paso ${step.iteration}`;
    case 'tool':
      return TOOL_LABELS[step.toolName ?? ''] ?? step.toolName ?? '';
    case 'final':
      return 'Respuesta final';
    case 'error':
      return step.cause === 'connection' ? 'Error de conexión' : 'Error';
    case 'narration':
    case 'notice':
      return step.text ?? '';
  }
}
