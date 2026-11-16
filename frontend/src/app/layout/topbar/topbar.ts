import { DecimalPipe, PercentPipe } from '@angular/common';
import { Component, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { SystemStatusStore } from '../../core/status/application/system-status.store';
import { LogoMark } from '../../core/ui/logo-mark/logo-mark';
import {
  DEMO_PROVIDER,
  ProviderStatus,
  prettyModelName,
  quotaText,
} from '../../core/status/domain/system-status';
import { ChatStore } from '../../features/planner/application/chat.store';
import { providerLabel } from './provider-label';

/** Cabecera fija: marca, navegación, modelo de IA en uso (con la cadena y su cuota) y aviso sobre el servicio. */
@Component({
  selector: 'app-topbar',
  imports: [DecimalPipe, PercentPipe, RouterLink, RouterLinkActive, LogoMark],
  templateUrl: './topbar.html',
  styleUrl: './topbar.scss',
  host: {
    '(document:click)': 'closeIfOutside($event)',
    '(document:keydown.escape)': 'closeAll()',
  },
})
export class Topbar {
  protected readonly status = inject(SystemStatusStore);
  protected readonly chat = inject(ChatStore);
  protected readonly demoProvider = DEMO_PROVIDER;

  /** Lo que dice el indicador: el modelo que responde o, en modo demo, por qué. */
  protected readonly chipText = computed(() => {
    if (!this.status.isDemo())
      return this.modelTitle(this.status.modelName(), providerLabel(this.status.provider()));
    const usage = this.status.usage();
    if (
      this.status.realAvailable() &&
      this.status.effectiveMode() === 'real' &&
      usage &&
      !usage.realAi
    ) {
      return 'Modo demo · cupo agotado';
    }
    return 'Modo demo';
  });

  /** Panel del indicador: toda la cadena de modelos, su cuota y la actividad del agente. */
  protected readonly modelOpen = signal(false);
  private readonly model = viewChild<ElementRef<HTMLElement>>('model');

  /** Panel de ayuda: explica que el backend gratuito se duerme y cómo despertarlo. */
  protected readonly infoOpen = signal(false);
  private readonly info = viewChild<ElementRef<HTMLElement>>('info');

  /** "Gemini 3.5 Flash-Lite"; si el nombre no dice quién lo sirve, se añade: "GPT-OSS 120B · Groq". */
  protected modelTitle(model: string, label: string): string {
    const name = model.includes(' ') || model === 'Modo demo' ? model : prettyModelName(model);
    return !label || name.toLowerCase().includes(label.toLowerCase()) ? name : `${name} · ${label}`;
  }

  protected quota(p: ProviderStatus): string {
    return quotaText(p);
  }

  protected toggleModel(): void {
    this.infoOpen.set(false);
    this.modelOpen.set(!this.modelOpen());
    if (this.modelOpen()) this.status.refresh();
  }

  protected toggleInfo(): void {
    this.modelOpen.set(false);
    this.infoOpen.set(!this.infoOpen());
  }

  protected toggleDemo(): void {
    this.status.setMode(this.status.preferredMode() === 'demo' ? 'real' : 'demo');
  }

  protected reload(): void {
    location.reload();
  }

  protected closeAll(): void {
    this.infoOpen.set(false);
    this.modelOpen.set(false);
  }

  protected closeIfOutside(event: Event): void {
    const target = event.target as Node;
    if (this.infoOpen() && !this.info()?.nativeElement.contains(target)) this.infoOpen.set(false);
    if (this.modelOpen() && !this.model()?.nativeElement.contains(target))
      this.modelOpen.set(false);
  }
}
