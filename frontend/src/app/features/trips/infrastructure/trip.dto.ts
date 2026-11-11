import { Trip } from '../domain/trip';

/** Forma exacta de un viaje en la API (snake_case). Solo se usa en esta capa. */

export interface ActivityDto {
  slot: string;
  name: string;
  category: string;
  duration_h: number;
  price_eur: number;
  area: string;
}

export interface TripDayDto {
  day: number;
  activities: ActivityDto[];
}

export interface BudgetDto {
  per_person: Record<string, number>;
  total_per_person_eur: number;
  total_eur: number;
  style: string;
  days: number;
  travelers: number;
}

export interface ClimateDto {
  month: string;
  avg_temp_c: number;
  rain_days: number;
  verdict: string;
}

export interface TripDto {
  id: number;
  created_at: string;
  title: string;
  destination_id: string;
  destination_name: string;
  flag: string;
  month: number | null;
  days: number;
  travelers: number;
  style: string;
  summary: string;
  climate: ClimateDto | null;
  budget: BudgetDto;
  itinerary: TripDayDto[];
}

/** Traduce el viaje de la API al modelo de dominio. Si la API cambia, solo cambia esto. */
export function toTrip(dto: TripDto): Trip {
  return {
    id: dto.id,
    createdAt: dto.created_at,
    title: dto.title,
    destinationId: dto.destination_id,
    destinationName: dto.destination_name,
    flag: dto.flag,
    month: dto.month,
    days: dto.days,
    travelers: dto.travelers,
    style: dto.style,
    summary: dto.summary,
    climate: dto.climate && {
      month: dto.climate.month,
      avgTempC: dto.climate.avg_temp_c,
      rainDays: dto.climate.rain_days,
      verdict: dto.climate.verdict,
    },
    budget: {
      perPerson: dto.budget.per_person,
      totalPerPersonEur: dto.budget.total_per_person_eur,
      totalEur: dto.budget.total_eur,
      style: dto.budget.style,
      days: dto.budget.days,
      travelers: dto.budget.travelers,
    },
    itinerary: dto.itinerary.map((day) => ({
      day: day.day,
      activities: day.activities.map((a) => ({
        slot: a.slot,
        name: a.name,
        category: a.category,
        durationHours: a.duration_h,
        priceEur: a.price_eur,
        area: a.area,
      })),
    })),
  };
}
