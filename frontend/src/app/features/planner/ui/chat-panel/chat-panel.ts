import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatMessage } from '../../domain/run';

/** Panel de conversación. Presentacional: recibe los mensajes y avisa de lo que hace el usuario. */
@Component({
  selector: 'app-chat-panel',
  imports: [FormsModule],
  templateUrl: './chat-panel.html',
  styleUrl: './chat-panel.scss',
})
export class ChatPanel {
  readonly messages = input.required<ChatMessage[]>();
  readonly running = input(false);

  readonly messageSent = output<string>();
  readonly stopped = output<void>();
  readonly conversationReset = output<void>();

  protected readonly draft = signal('');
  /** Queda contenido por debajo de lo visible: se avisa con un botón para bajar. */
  protected readonly hasMore = signal(false);
  private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');

  protected readonly suggestions = [
    '5 días en Kioto en abril con mi pareja, nos encanta la gastronomía y la historia',
    'Sorpréndeme: un fin de semana barato con playa en mayo',
    'Una semana en Islandia en febrero para ver auroras, 2 personas',
    '4 días en Ciudad de México en noviembre, comida y arte, estilo lujo',
    '¿Necesito visado para viajar a Japón?',
  ];

  constructor() {
    // Baja al último mensaje cada vez que cambia la conversación (sin mensajes, se queda arriba).
    effect(() => {
      const chatting = this.messages().length > 0;
      this.running();
      queueMicrotask(() => {
        if (chatting) this.scrollToEnd();
        this.checkMore();
      });
    });

    // El espacio disponible cambia al girar el móvil, abrir el teclado o volver a esta pestaña.
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      const el = this.scroller()?.nativeElement;
      if (!el || typeof ResizeObserver !== 'function') return;
      const observer = new ResizeObserver(() => this.checkMore());
      observer.observe(el);
      destroyRef.onDestroy(() => observer.disconnect());
    });
  }

  protected scrollToEnd(): void {
    const el = this.scroller()?.nativeElement;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }

  protected checkMore(): void {
    const el = this.scroller()?.nativeElement;
    if (el) this.hasMore.set(el.scrollHeight - el.scrollTop - el.clientHeight > 24);
  }

  protected send(text: string): void {
    this.messageSent.emit(text);
    this.draft.set('');
  }

  protected onEnter(event: Event): void {
    if (!(event as KeyboardEvent).shiftKey) {
      event.preventDefault();
      this.send(this.draft());
    }
  }

  /** Texto que se enseña en la burbuja: los fallos se explican en lenguaje de usuario. */
  protected textOf(message: ChatMessage): string {
    if (message.role !== 'failure') return message.text;
    return message.cause === 'connection'
      ? 'No he podido contactar con el servidor. ¿Está el backend arrancado?'
      : `Algo ha fallado: ${message.text}`;
  }
}
