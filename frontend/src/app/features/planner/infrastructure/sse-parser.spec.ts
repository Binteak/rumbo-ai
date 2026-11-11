import { SseParser } from './sse-parser';

describe('SseParser', () => {
  it('emite un evento por cada bloque completo', () => {
    const parser = new SseParser();

    expect(
      parser.push(
        'data: {"type":"thinking","iteration":1}\n\ndata: {"type":"final","text":"ok"}\n\n',
      ),
    ).toEqual([
      { type: 'thinking', iteration: 1 },
      { type: 'final', text: 'ok' },
    ]);
  });

  it('espera al resto cuando un evento llega partido en dos trozos', () => {
    const parser = new SseParser();

    expect(parser.push('data: {"type":"fin')).toEqual([]);
    expect(parser.push('al","text":"ok"}\n\n')).toEqual([{ type: 'final', text: 'ok' }]);
  });

  it('ignora los bloques sin datos, como los comentarios de keep-alive', () => {
    const parser = new SseParser();

    expect(parser.push(': ping\n\ndata: {"type":"thinking","iteration":2}\n\n')).toEqual([
      { type: 'thinking', iteration: 2 },
    ]);
  });
});
