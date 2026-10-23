import { Component, computed, input, output } from '@angular/core';
import { ProposedAction } from '../api.service';
import { eur } from '../format';

export type ActionState = { status: 'pending' | 'working' | 'confirmed' | 'dismissed' | 'error'; message?: string };

const TITLES: Record<ProposedAction['type'], { title: string; cta: string; note: string }> = {
  cart_add: { title: 'Cart proposal', cta: 'Add to cart', note: 'Nothing is ordered until you confirm.' },
  quote_request: { title: 'Quote request for your sales rep', cta: 'Send to sales rep', note: 'Your sales rep decides on price and terms.' },
  handoff: { title: 'Hand over to your sales rep', cta: 'Send to sales rep', note: 'Your sales rep will follow up.' },
};

/**
 * Human-in-the-loop: the agent only proposes. This card is the confirmation step,
 * and confirming calls deterministic code on the server, not the LLM.
 */
@Component({
  selector: 'app-action-card',
  template: `
    <article class="action" [class.done]="state().status === 'confirmed'">
      <header>
        <span class="badge" [class]="'badge ' + (action().type === 'cart_add' ? 'accent' : 'warning')">
          {{ action().type === 'cart_add' ? '🛒' : '↗' }} {{ meta().title }}
        </span>
        <span class="mono id">{{ action().action_id }}</span>
      </header>

      @if (action().payload.lines?.length) {
        <div class="table-scroll">
          <table class="data compact">
            <thead><tr><th>SKU</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Total</th></tr></thead>
            <tbody>
              @for (line of action().payload.lines; track line.sku) {
                <tr>
                  <td><span class="mono">{{ line.sku }}</span> @if (!line.in_stock) { <span class="badge warning small">backorder</span> }</td>
                  <td class="num">{{ line.quantity }}</td>
                  <td class="num">{{ eur(line.unit_price) }}</td>
                  <td class="num">{{ eur(line.line_total) }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <p class="totals">
          Net <strong>{{ eur(action().payload.net_total) }}</strong>
          @if (action().payload.shipping !== undefined && action().type === 'cart_add') { · shipping {{ eur(action().payload.shipping) }} }
          <span class="muted">excl. VAT</span>
        </p>
      } @else {
        <p class="summary">{{ action().summary }}</p>
      }

      @if (action().payload.quote_reasons?.length) {
        <p class="reasons">Why a quote: {{ action().payload.quote_reasons!.join('; ') }}</p>
      }
      @if (action().payload.requested_discount_pct) {
        <p class="reasons">Requested discount: {{ action().payload.requested_discount_pct }}%</p>
      }

      <footer>
        @switch (state().status) {
          @case ('pending') {
            <span class="muted note">{{ meta().note }}</span>
            <span class="buttons">
              <button type="button" class="btn small" (click)="dismiss.emit()">Dismiss</button>
              <button type="button" class="btn small primary" (click)="confirm.emit()">{{ meta().cta }}</button>
            </span>
          }
          @case ('working') { <span class="muted">Working…</span> }
          @case ('confirmed') { <span class="badge good">✓ {{ state().message }}</span> }
          @case ('dismissed') { <span class="badge neutral">Dismissed</span> }
          @case ('error') { <span class="badge critical">✕ {{ state().message }}</span> }
        }
      </footer>
    </article>
  `,
  styles: `
    .action {
      margin-top: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md);
      border: 1px solid var(--border); background: var(--surface-2);
    }
    .action.done { border-color: var(--good); }
    header { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); margin-bottom: var(--space-2); }
    .id { font-size: 11.5px; color: var(--text-muted); }
    table.compact { font-size: 13px; }
    table.compact th, table.compact td { padding: 4px 6px; }
    .badge.small { font-size: 10.5px; padding: 0 6px; }
    .totals, .summary, .reasons { margin: 8px 0 0; font-size: 13.5px; }
    .reasons { color: var(--text-secondary); }
    footer { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin-top: var(--space-3); }
    .note { font-size: 12.5px; }
    .buttons { display: flex; gap: var(--space-2); }
  `,
})
export class ActionCardComponent {
  readonly action = input.required<ProposedAction>();
  readonly state = input<ActionState>({ status: 'pending' });
  readonly confirm = output<void>();
  readonly dismiss = output<void>();
  readonly meta = computed(() => TITLES[this.action().type]);
  readonly eur = eur;
}
