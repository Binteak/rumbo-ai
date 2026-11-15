import { TestBed } from '@angular/core/testing';
import { LogoMark } from './logo-mark';

describe('LogoMark', () => {
  it('dibuja el catalejo como icono decorativo con el color del texto', async () => {
    const fixture = TestBed.createComponent(LogoMark);
    await fixture.whenStable();
    const svg = (fixture.nativeElement as HTMLElement).querySelector('svg');

    expect(svg?.getAttribute('aria-hidden')).toBe('true');
    expect(svg?.getAttribute('fill')).toBe('currentColor');
    expect(svg?.querySelectorAll('rect').length).toBe(4);
  });
});
