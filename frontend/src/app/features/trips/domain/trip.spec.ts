import { aTrip } from '../testing/trip.fixture';
import { budgetBreakdown, dayCost, dayHours } from './trip';

describe('dominio de viajes', () => {
  const trip = aTrip();

  it('suma las horas y el coste de las actividades de un día', () => {
    expect(dayHours(trip.itinerary[0])).toBe(5.5);
    expect(dayCost(trip.itinerary[0])).toBe(28);
  });

  it('desglosa el presupuesto para todo el grupo y compara cada partida con la mayor', () => {
    const lines = budgetBreakdown(trip.budget);

    expect(lines.map((l) => l.key)).toEqual([
      'alojamiento',
      'comida',
      'transporte_local',
      'actividades',
    ]);
    expect(lines[0]).toEqual({ key: 'alojamiento', totalEur: 360, share: 100 });
    expect(lines[2].totalEur).toBe(80);
    expect(lines[2].share).toBeCloseTo(22.22, 2);
  });

  it('no divide entre cero si el presupuesto viene vacío', () => {
    expect(budgetBreakdown({ ...trip.budget, perPerson: {} })).toEqual([]);
    expect(budgetBreakdown({ ...trip.budget, perPerson: { comida: 0 } })[0].share).toBe(0);
  });
});
