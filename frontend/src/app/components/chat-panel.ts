import { Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AgentStore } from '../core/agent.store';

@Component({
  selector: 'app-chat-panel',
  imports: [FormsModule],
  template: `
    <section class="panel chat">
      <header class="panel-head">
        <div>
          <p class="eyebrow">Conversación</p>
          <h2>¿A dónde vamos?</h2>
        </div>
        <button class="ghost" (click)="store.newConversation()" [disabled]="!store.messages().length">Nueva</button>
      </header>

      <div class="messages" #scroller>
        @if (!store.messages().length) {
          <div class="empty">
            <p>Describe tu viaje con tus palabras. El agente decidirá qué herramientas usar y verás cada paso en directo.</p>
            <div class="suggestions">
              @for (s of suggestions; track s) {
                <button class="chip-btn" (click)="send(s)" [disabled]="store.running()">{{ s }}</button>
              }
            </div>
          </div>
        }
        @for (m of store.messages(); track $index) {
          @if (m.role === 'notice') {
            <p class="chat-notice">{{ m.text }}</p>
          } @else {
            <div class="msg" [class.user]="m.role === 'user'">
              <span class="avatar">{{ m.role === 'user' ? 'Tú' : 'R' }}</span>
              <p>{{ m.text }}</p>
            </div>
          }
        }
        @if (store.running()) {
          <div class="msg">
            <span class="avatar">R</span>
            <p class="typing"><i></i><i></i><i></i></p>
          </div>
        }
      </div>

      <form class="composer" (ngSubmit)="send(draft())">
        <textarea
          name="draft"
          rows="2"
          [ngModel]="draft()"
          (ngModelChange)="draft.set($event)"
          (keydown.enter)="onEnter($event)"
          placeholder="Ej.: 4 días en Lisboa en junio, gastronomía y miradores"
          maxlength="1000"
        ></textarea>
        @if (store.running()) {
          <button type="button" class="send stop" (click)="store.stop()" aria-label="Detener">■</button>
        } @else {
          <button type="submit" class="send" [disabled]="!draft().trim()" aria-label="Enviar">➜</button>
        }
      </form>
    </section>
  `,
})
export class ChatPanel {
  protected readonly store = inject(AgentStore);
  protected readonly draft = signal('');
  private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');

  protected readonly suggestions = [
    '5 días en Kioto en abril con mi pareja, nos encanta la gastronomía y la historia',
    'Sorpréndeme: un fin de semana barato con playa en mayo',
    'Una semana en Islandia en febrero para ver auroras, 2 personas',
    '4 días en Ciudad de México en noviembre, comida y arte, estilo lujo',
    '¿Necesito visado para viajar a Japón?',
  ];

  constructor() {
    effect(() => {
      this.store.messages();
      this.store.running();
      queueMicrotask(() => {
        const el = this.scroller()?.nativeElement;
        if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      });
    });
  }

  protected send(text: string): void {
    this.store.send(text);
    this.draft.set('');
  }

  protected onEnter(event: Event): void {
    const e = event as KeyboardEvent;
    if (!e.shiftKey) {
      e.preventDefault();
      this.send(this.draft());
    }
  }
}
