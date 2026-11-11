import { Trip } from '../domain/trip';
import { TripDto } from '../infrastructure/trip.dto';

/** Viaje tal y como lo devuelve la API, para los tests de adaptadores. */
export function aTripDto(overrides: Partial<TripDto> = {}): TripDto {
  return {
    id: 9,
    created_at: '2026-11-10T10:00:00+00:00',
    title: '3 días en Seúl en mayo',
    destination_id: 'seul',
    destination_name: 'Seúl',
    flag: '🇰🇷',
    month: 5,
    days: 3,
    travelers: 2,
    style: 'confort',
    summary: 'Palacios, mercados y barrios creativos.',
    climate: {
      month: 'mayo',
      avg_temp_c: 18,
      rain_days: 8,
      verdict: 'buen momento para visitarlo',
    },
    budget: {
      per_person: { alojamiento: 180, comida: 120, transporte_local: 40, actividades: 60 },
      total_per_person_eur: 400,
      total_eur: 800,
      style: 'confort',
      days: 3,
      travelers: 2,
    },
    itinerary: [
      {
        day: 1,
        activities: [
          {
            slot: 'mañana',
            name: 'Palacio Gyeongbokgung',
            category: 'historia',
            duration_h: 3,
            price_eur: 3,
            area: 'Jongno',
          },
          {
            slot: 'noche',
            name: 'Cena en Hongdae',
            category: 'nocturna',
            duration_h: 2.5,
            price_eur: 25,
            area: 'Hongdae',
          },
        ],
      },
    ],
    ...overrides,
  };
}

/** El mismo viaje en el modelo de dominio, para los tests de stores y componentes. */
export function aTrip(overrides: Partial<Trip> = {}): Trip {
  return {
    id: 9,
    createdAt: '2026-11-10T10:00:00+00:00',
    title: '3 días en Seúl en mayo',
    destinationId: 'seul',
    destinationName: 'Seúl',
    flag: '🇰🇷',
    month: 5,
    days: 3,
    travelers: 2,
    style: 'confort',
    summary: 'Palacios, mercados y barrios creativos.',
    climate: { month: 'mayo', avgTempC: 18, rainDays: 8, verdict: 'buen momento para visitarlo' },
    budget: {
      perPerson: { alojamiento: 180, comida: 120, transporte_local: 40, actividades: 60 },
      totalPerPersonEur: 400,
      totalEur: 800,
      style: 'confort',
      days: 3,
      travelers: 2,
    },
    itinerary: [
      {
        day: 1,
        activities: [
          {
            slot: 'mañana',
            name: 'Palacio Gyeongbokgung',
            category: 'historia',
            durationHours: 3,
            priceEur: 3,
            area: 'Jongno',
          },
          {
            slot: 'noche',
            name: 'Cena en Hongdae',
            category: 'nocturna',
            durationHours: 2.5,
            priceEur: 25,
            area: 'Hongdae',
          },
        ],
      },
    ],
    ...overrides,
  };
}
