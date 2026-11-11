import { DecimalPipe, JsonPipe, SlicePipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { RunStats } from '../../domain/agent-event';
import { TraceStep, thinkingCount, toolSteps } from '../../domain/run';
import { stepTitle } from './step-title';

/** Traza del agente en directo. Presentacional: pinta los pasos que recibe. */
@Component({
  selector: 'app-trace-panel',
  imports: [JsonPipe, DecimalPipe, SlicePipe],
  templateUrl: './trace-panel.html',
  styleUrl: './trace-panel.scss',
})
export class TracePanel {
  readonly trace = input.required<TraceStep[]>();
  readonly running = input(false);
  readonly tokens = input({ input: 0, output: 0 });
  readonly lastRun = input<RunStats | null>(null);

  protected readonly toolCount = computed(() => toolSteps(this.trace()).length);
  /** Mientras el turno no termina, los pasos son los "razonando" vistos hasta ahora. */
  protected readonly iterations = computed(
    () => this.lastRun()?.iterations ?? thinkingCount(this.trace()),
  );
  protected readonly totalTokens = computed(() => this.tokens().input + this.tokens().output);
  protected readonly title = stepTitle;
}
