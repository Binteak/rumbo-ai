/** Dominio de viajes: TypeScript puro, sin Angular ni detalles de la API. */

export interface Activity {
  slot: string;
  name: string;
  category: string;
  durationHours: number;
  priceEur: number;
  area: string;
}

export interface TripDay {
  day: number;
  activities: Activity[];
}

export interface Budget {
  /** Gasto por persona de cada partida (alojamiento, comida...). */
  perPerson: Record<string, number>;
  totalPerPersonEur: number;
  totalEur: number;
  style: string;
  days: number;
  travelers: number;
}

export interface Climate {
  month: string;
  avgTempC: number;
  rainDays: number;
  verdict: string;
}

export interface Trip {
  id: number;
  createdAt: string;
  title: string;
  destinationId: string;
  destinationName: string;
  flag: string;
  month: number | null;
  days: number;
  travelers: number;
  style: string;
  summary: string;
  climate: Climate | null;
  budget: Budget;
  itinerary: TripDay[];
}

/** Partida del presupuesto para todo el grupo y su peso frente a la partida mayor (0-100). */
export interface BudgetLine {
  key: string;
  totalEur: number;
  share: number;
}

export function dayHours(day: TripDay): number {
  return day.activities.reduce((sum, a) => sum + a.durationHours, 0);
}

export function dayCost(day: TripDay): number {
  return day.activities.reduce((sum, a) => sum + a.priceEur, 0);
}

export function budgetBreakdown(budget: Budget): BudgetLine[] {
  const entries = Object.entries(budget.perPerson);
  const max = Math.max(0, ...entries.map(([, value]) => value));
  return entries.map(([key, value]) => ({
    key,
    totalEur: value * budget.travelers,
    share: max ? (value / max) * 100 : 0,
  }));
}
