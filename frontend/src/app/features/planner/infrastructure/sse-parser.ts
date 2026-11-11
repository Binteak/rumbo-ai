/**
 * Parser incremental de Server-Sent Events.
 *
 * El stream llega en trozos de tamaño arbitrario: un evento puede venir partido en dos trozos
 * o varios eventos en uno solo. Se acumula el texto y se emite cada bloque completo
 * (separado por una línea en blanco), ya convertido de JSON.
 */
export class SseParser {
  private buffer = '';

  push(chunk: string): unknown[] {
    this.buffer += chunk;
    const blocks = this.buffer.split('\n\n');
    this.buffer = blocks.pop() ?? '';
    const events: unknown[] = [];
    for (const block of blocks) {
      const line = block.split('\n').find((l) => l.startsWith('data: '));
      if (line) events.push(JSON.parse(line.slice(6)));
    }
    return events;
  }
}
