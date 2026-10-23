import { Component, computed, input } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { AgentResponse, TraceEvent } from '../api.service';

const KIND_LABELS: Record<TraceEvent['kind'], string> = {
  router: 'Router', llm: 'LLM', tool: 'Tool', guard: 'Guard', fallback: 'Fallback', action: 'Proposal',
};
const STATUS: Record<TraceEvent['status'], { tone: string; icon: string; label: string }> = {
  ok: { tone: 'good', icon: '✓', label: 'ok' },
  fallback: { tone: 'warning', icon: '↩', label: 'fallback' },
  error: { tone: 'critical', icon: '✕', label: 'error' },
  blocked: { tone: 'critical', icon: '⛔', label: 'blocked' },
  skipped: { tone: 'neutral', icon: '–', label: 'skipped' },
};

/** Shows how the agent reached its answer: routing decision, tool scope, every step, guards and fallbacks. */
@Component({
  selector: 'app-trace-panel',
  imports: [DecimalPipe],
  template: `
    @if (response(); as r) {
      <section class="block">
        <h3><span class="step">1</span> Router decision</h3>
        <div class="chips">
          @for (intent of r.intents; track intent) { <span class="chip accent">{{ intent.replace('_', ' ') }}</span> }
          @if (!r.intents.length) { <span class="chip">none</span> }
        </div>
        @if (r.rationale) { <p class="rationale">“{{ r.rationale }}”</p> }
      </section>

      <section class="block">
        <h3><span class="step">2</span> Tools unlocked (least privilege)</h3>
        <div class="chips">
          @for (tool of r.allowed_tools; track tool) { <span class="chip mono" [class.used]="used().has(tool)">{{ tool }}</span> }
          @if (!r.allowed_tools.length) { <span class="muted small">No tools: declined before the agent ran.</span> }
        </div>
        <p class="hint muted">Highlighted tools were actually called.</p>
      </section>

      <section class="block">
        <h3><span class="step">3</span> Steps</h3>
        <ol class="timeline">
          @for (e of r.trace; track $index) {
            <li [class]="'ev ' + status[e.status].tone">
              <div class="ev-head">
                <span class="kind">{{ kinds[e.kind] }}</span>
                <span class="mono name">{{ e.name }}</span>
                <span class="badge" [class]="'badge ' + status[e.status].tone">{{ status[e.status].icon }} {{ status[e.status].label }}</span>
                @if (e.latency_ms !== null) { <span class="ms">{{ e.latency_ms | number }} ms</span> }
              </div>
              <p class="detail">{{ e.detail }}</p>
            </li>
          }
        </ol>
      </section>

      <section class="block">
        <h3><span class="step">4</span> Output guard</h3>
        @if (r.verification; as v) {
          @if (v.passed) {
            <span class="badge good">✓ {{ v.amounts_checked }} prices and {{ v.citations_checked }} citations verified against tool results</span>
          } @else {
            <span class="badge critical">✕ Unverified: {{ v.unverified_amounts.concat(v.invalid_citations).join(', ') }}</span>
          }
        } @else {
          <span class="badge neutral">– Not run (request declined)</span>
        }
      </section>

      <section class="block meta">
        <div><dt>Total time</dt><dd>{{ r.latency_ms / 1000 | number: '1.1-1' }} s</dd></div>
        <div><dt>LLM calls</dt><dd>{{ r.models_used.length }}</dd></div>
        <div><dt>Models</dt><dd>{{ models() }}</dd></div>
        <div><dt>Fallbacks</dt><dd>{{ r.fallbacks.length ? r.fallbacks.join(', ') : 'none' }}</dd></div>
      </section>
    } @else {
      <p class="empty muted">Ask something to see how the agent decides: which intents the router detects, which tools it unlocks, each tool call, the guard result and any fallbacks.</p>
    }
  `,
  styles: `
    :host { display: block; }
    .block { padding: var(--space-3) 0; border-bottom: 1px solid var(--border); }
    .block:last-child { border-bottom: 0; }
    h3 { display: flex; align-items: center; gap: var(--space-2); margin: 0 0 var(--space-2); font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--text-secondary); }
    .step {
      width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center;
      background: var(--accent-soft); color: var(--accent-text); font-size: 11.5px;
    }
    .chips { display: flex; flex-wrap: wrap; gap: var(--space-1); }
    .chip.mono { font-family: var(--font-mono); font-size: 11.5px; }
    .chip.used { background: var(--accent-soft); color: var(--accent-text); font-weight: 600; }
    .rationale { margin: var(--space-2) 0 0; font-size: 13px; color: var(--text-secondary); font-style: italic; }
    .hint, .small { margin: 6px 0 0; font-size: 12px; }
    .timeline { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
    .ev { padding: 7px 9px; border-radius: var(--radius-md); background: var(--surface-2); border-left: 3px solid var(--border); }
    .ev.good { border-left-color: var(--good); }
    .ev.warning { border-left-color: var(--warning); background: var(--warning-soft); }
    .ev.critical { border-left-color: var(--critical); background: var(--critical-soft); }
    .ev-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .kind { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); }
    .name { font-size: 12.5px; font-weight: 600; }
    .badge { font-size: 10.5px; padding: 0 7px; }
    .ms { margin-left: auto; font-size: 11.5px; color: var(--text-muted); font-variant-numeric: tabular-nums; }
    .detail { margin: 3px 0 0; font-size: 12.5px; color: var(--text-secondary); overflow-wrap: anywhere; }
    .meta { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12.5px; margin: 0; }
    .meta dt { color: var(--text-muted); }
    .meta dd { margin: 0; overflow-wrap: anywhere; }
    .empty { font-size: 13.5px; }
  `,
})
export class TracePanelComponent {
  readonly response = input<AgentResponse | null>(null);
  readonly kinds = KIND_LABELS;
  readonly status = STATUS;
  readonly used = computed(() => new Set((this.response()?.trace ?? []).filter(e => e.kind === 'tool').map(e => e.name)));
  readonly models = computed(() => [...new Set(this.response()?.models_used ?? [])].join(', ') || '–');
}
