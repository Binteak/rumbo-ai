import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ChatMessage } from '../../domain/run';
import { ChatPanel } from './chat-panel';

describe('ChatPanel', () => {
  let fixture: ComponentFixture<ChatPanel>;
  let el: HTMLElement;

  async function render(messages: ChatMessage[], running = false): Promise<void> {
    fixture.componentRef.setInput('messages', messages);
    fixture.componentRef.setInput('running', running);
    await fixture.whenStable();
  }

  beforeEach(() => {
    // jsdom no implementa el scroll de elementos.
    Element.prototype.scrollTo = () => undefined;
    fixture = TestBed.createComponent(ChatPanel);
    el = fixture.nativeElement;
  });

  it('sin mensajes ofrece sugerencias y al pulsar una la envía', async () => {
    const sent: string[] = [];
    fixture.componentInstance.messageSent.subscribe((text) => sent.push(text));
    await render([]);

    const suggestions = el.querySelectorAll<HTMLButtonElement>('.chip-btn');
    expect(suggestions.length).toBe(5);
    suggestions[4].click();

    expect(sent).toEqual(['¿Necesito visado para viajar a Japón?']);
  });

  it('pinta cada mensaje según quién lo dice', async () => {
    await render([
      { role: 'user', text: '3 días en Lisboa' },
      { role: 'notice', text: 'Respondo en modo demo.' },
      { role: 'agent', text: 'Aquí tienes el plan.' },
    ]);

    expect(el.querySelector('.msg.user p')?.textContent).toBe('3 días en Lisboa');
    expect(el.querySelector('.chat-notice')?.textContent).toBe('Respondo en modo demo.');
    expect(el.querySelector('.msg:not(.user) p')?.textContent).toBe('Aquí tienes el plan.');
    expect(el.querySelector('.empty')).toBeNull();
  });

  it('explica los fallos en lenguaje de usuario', async () => {
    await render([
      { role: 'failure', cause: 'connection', text: 'Failed to fetch' },
      { role: 'failure', cause: 'agent', text: 'ValueError: x' },
    ]);

    const texts = [...el.querySelectorAll('.msg p')].map((p) => p.textContent);
    expect(texts).toEqual([
      'No he podido contactar con el servidor. ¿Está el backend arrancado?',
      'Algo ha fallado: ValueError: x',
    ]);
  });

  it('envía lo escrito al enviar el formulario y vacía la caja', async () => {
    const sent: string[] = [];
    fixture.componentInstance.messageSent.subscribe((text) => sent.push(text));
    await render([]);

    const textarea = el.querySelector('textarea')!;
    textarea.value = '4 días en Kioto';
    textarea.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();

    expect(sent).toEqual(['4 días en Kioto']);
    expect(textarea.value).toBe('');
  });

  it('mientras el agente trabaja cambia Enviar por Detener', async () => {
    let stopped = 0;
    fixture.componentInstance.stopped.subscribe(() => stopped++);
    await render([{ role: 'user', text: 'hola' }], true);

    expect(el.querySelector('.typing')).not.toBeNull();
    expect(el.querySelector('button[type="submit"]')).toBeNull();
    el.querySelector<HTMLButtonElement>('.send.stop')!.click();

    expect(stopped).toBe(1);
  });

  it('"Nueva" solo se puede pulsar si hay conversación', async () => {
    let resets = 0;
    fixture.componentInstance.conversationReset.subscribe(() => resets++);
    await render([]);
    const button = el.querySelector<HTMLButtonElement>('.ghost')!;
    expect(button.disabled).toBe(true);

    await render([{ role: 'user', text: 'hola' }]);
    button.click();

    expect(button.disabled).toBe(false);
    expect(resets).toBe(1);
  });
});
