import { DecimalPipe, JsonPipe, SlicePipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { AgentStore } from '../core/agent.store';

@Component({
  selector: 'app-trace-panel',
  imports: [JsonPipe, DecimalPipe, SlicePipe],
  template: `
    <section class="panel trace">
      <header class="panel-head">
        <div>
          <p class="eyebrow">Observabilidad</p>
          <h2>Traza del agente</h2>
        </div>
        @if (store.running()) {
          <span class="live"><i></i>En directo</span>
        }
      </header>

      <div class="metrics">
        <div><span>Pasos</span><strong>{{ store.lastRun()?.iterations ?? thinkingSteps() }}</strong></div>
        <div><span>Herramientas</span><strong>{{ store.toolSteps().length }}</strong></div>
        <div><span>Tokens</span><strong>{{ store.tokens().input + store.tokens().output | number }}</strong></div>
        <div>
          <span>Tiempo</span>
          <strong>{{ store.lastRun() ? (store.lastRun()!.duration_ms / 1000 | number: '1.1-1') + ' s' : '—' }}</strong>
        </div>
      </div>

      <ol class="timeline">
        @for (step of store.trace(); track step.id) {
          <li class="step" [class]="step.kind + ' ' + step.status">
            <span class="dot"></span>
            <div class="step-body">
              <div class="step-title">
                <span>{{ step.title }}</span>
                @if (step.duration_ms !== undefined) {
                  <small>{{ step.duration_ms }} ms</small>
                }
              </div>
              @if (step.kind === 'tool') {
                <code class="fn">{{ step.detail }}()</code>
                @if (step.rag; as rag) {
                  <div class="rag">
                    <p class="rag-meta">
                      {{ rag.retrieval === 'hybrid' ? 'Búsqueda híbrida · BM25 + vectores' : 'Solo BM25 (vectores no disponibles)' }}
                      @if (rag.destination_id) {
                        · filtro: {{ rag.destination_id }}
                      }
                    </p>
                    @if (rag.results.length) {
                      <ol class="sources">
                        @for (hit of rag.results; track hit.source + hit.section) {
                          <li>
                            <div class="source-head">
                              <strong>{{ hit.destination }} · {{ hit.section }}</strong>
                              <span class="ranks">
                                @if (hit.match.bm25_rank) {
                                  <i>BM25 #{{ hit.match.bm25_rank }}</i>
                                }
                                @if (hit.match.vector_rank) {
                                  <i>vector #{{ hit.match.vector_rank }}</i>
                                }
                              </span>
                            </div>
                            <p>{{ hit.text | slice: 0 : 160 }}{{ hit.text.length > 160 ? '…' : '' }}</p>
                            <small>{{ hit.source }} · score {{ hit.score | number: '1.3-3' }}</small>
                          </li>
                        }
                      </ol>
                    } @else {
                      <p class="rag-empty">Sin resultados en las guías: el agente no debe inventar la respuesta.</p>
                    }
                  </div>
                }
                <details>
                  <summary>Entrada y salida</summary>
                  <p class="label">input</p>
                  <pre>{{ step.input | json }}</pre>
                  @if (step.output) {
                    <p class="label">{{ step.status === 'error' ? 'error' : 'output' }}</p>
                    <pre [class.err]="step.status === 'error'">{{ step.output | json }}</pre>
                  }
                </details>
              } @else if (step.detail) {
                <p class="detail">{{ step.detail }}</p>
              }
            </div>
          </li>
        } @empty {
          <li class="placeholder">
            Aquí verás cómo razona el agente: cada llamada a herramienta, sus argumentos, el resultado y cuánto tarda.
          </li>
        }
      </ol>
    </section>
  `,
})
export class TracePanel {
  protected readonly store = inject(AgentStore);
  protected thinkingSteps(): number {
    return this.store.trace().filter((s) => s.kind === 'thinking').length;
  }
}
