import { Component, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, Ticket } from '../../api.service';
import { eur } from '../../format';

@Component({
  selector: 'app-seller-page',
  imports: [DatePipe, FormsModule, RouterLink],
  template: `
    <div class="container">
      <header class="page-head">
        <span class="eyebrow">Seller journey</span>
        <h1>Seller desk</h1>
        <p>
          When a buyer's request needs a human (credit limit, quote threshold, discount request, prepayment
          account or a complaint), the agent prepares it and the buyer confirms sending it here. The sales rep
          sees the full context and decides. The agent never approves its own proposals.
        </p>
      </header>

      <div class="bar">
        <div class="segmented" role="group" aria-label="Filter">
          <button type="button" [class.on]="filter() === 'open'" (click)="filter.set('open')">Open {{ openCount() }}</button>
          <button type="button" [class.on]="filter() === 'all'" (click)="filter.set('all')">All {{ tickets().length }}</button>
        </div>
        <button type="button" class="btn small" (click)="load()">↻ Refresh</button>
      </div>

      @if (visible().length === 0) {
        <div class="card empty">
          <h2>No {{ filter() === 'open' ? 'open ' : '' }}requests yet</h2>
          <p class="sub">
            Try it: on the <a routerLink="/">Assistant</a>, sign in as XYZ Construction and ask
            <em>“Can you give me 25% off if I buy 100 boxes of FAS-1001?”</em>, or as ABC Engineering ask to
            <em>“Add 400 TLS-4001 cordless drills to my cart”</em>. Confirm the proposal, then come back here.
          </p>
        </div>
      }

      @for (t of visible(); track t.ticket_id) {
        <article class="card ticket">
          <header>
            <div>
              <span class="badge" [class]="'badge ' + (t.type === 'handoff' ? 'accent' : 'warning')">
                {{ t.type === 'handoff' ? '↗ Handoff' : '◐ Quote request' }}
              </span>
              <h2>{{ t.company }} <span class="muted mono id">{{ t.ticket_id }}</span></h2>
              <p class="muted meta">Account {{ t.account_id }} · assigned to {{ t.sales_rep }} · {{ t.created_at | date: 'medium' }}</p>
            </div>
            @switch (t.status) {
              @case ('approved') { <span class="badge good">✓ Approved</span> }
              @case ('rejected') { <span class="badge critical">✕ Rejected</span> }
              @default { <span class="badge neutral">● Open</span> }
            }
          </header>

          <div class="brief">
            <h3>Agent-prepared brief</h3>
            <p>{{ t.summary }}</p>
            @if (t.payload.quote_reasons?.length) {
              <p><strong>Business rules triggered:</strong> {{ t.payload.quote_reasons!.join('; ') }}</p>
            }
            @if (t.payload.requested_discount_pct) {
              <p><strong>Requested discount:</strong> {{ t.payload.requested_discount_pct }}% on top of the current price</p>
            }
            @if (t.payload.reason) { <p><strong>Buyer's reason:</strong> {{ t.payload.reason }}</p> }
            <p class="recommendation"><strong>Suggested next step:</strong> {{ recommendation(t) }}</p>
          </div>

          @if (t.payload.lines?.length) {
            <div class="table-scroll">
              <table class="data">
                <thead><tr><th>SKU</th><th>Product</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Total</th><th>Stock</th></tr></thead>
                <tbody>
                  @for (l of t.payload.lines; track l.sku) {
                    <tr>
                      <td class="mono">{{ l.sku }}</td><td>{{ l.name }}</td><td class="num">{{ l.quantity }}</td>
                      <td class="num">{{ eur(l.unit_price) }}</td><td class="num">{{ eur(l.line_total) }}</td>
                      <td>@if (l.in_stock) { <span class="badge good">● in stock</span> } @else { <span class="badge warning">◐ backorder</span> }</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
            <p class="total">Net total <strong>{{ eur(t.payload.net_total) }}</strong> <span class="muted">excl. VAT</span></p>
          }

          @if (t.status === 'open') {
            <div class="decide">
              <input type="text" [(ngModel)]="notes[t.ticket_id]" placeholder="Note to the buyer (optional)" maxlength="500" aria-label="Decision note" />
              <button type="button" class="btn small" (click)="decide(t, 'reject')">Reject</button>
              <button type="button" class="btn small primary" (click)="decide(t, 'approve')">Approve quote</button>
            </div>
          } @else if (t.decision_note) {
            <p class="muted">Note: {{ t.decision_note }}</p>
          }
        </article>
      }
    </div>
  `,
  styles: `
    .bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4); }
    .segmented { display: inline-flex; padding: 3px; border-radius: var(--radius-md); background: var(--surface-2); }
    .segmented button { border: 0; background: transparent; padding: 6px 12px; border-radius: 8px; font-size: 13px; cursor: pointer; color: var(--text-secondary); }
    .segmented button.on { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: var(--shadow); }
    .ticket { margin-bottom: var(--space-4); }
    .ticket header { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-3); }
    .ticket h2 { margin: 6px 0 0; }
    .id { font-size: 12px; font-weight: 400; }
    .meta { margin: 2px 0 0; font-size: 13px; }
    .brief { margin: var(--space-4) 0; padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--surface-2); font-size: 14px; }
    .brief h3 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); }
    .brief p { margin: 4px 0; }
    .recommendation { color: var(--accent-text); }
    .total { margin: var(--space-3) 0 0; font-size: 14px; }
    .decide { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }
    .decide input { flex: 1; min-width: 200px; padding: 7px 10px; border-radius: var(--radius-md); border: 1px solid var(--border); background: var(--surface); }
    .empty em { color: var(--text); }
  `,
})
export class SellerPageComponent {
  private api = inject(ApiService);
  readonly tickets = signal<Ticket[]>([]);
  readonly filter = signal<'open' | 'all'>('open');
  readonly visible = computed(() => this.filter() === 'open' ? this.tickets().filter(t => t.status === 'open') : this.tickets());
  readonly openCount = computed(() => this.tickets().filter(t => t.status === 'open').length);
  readonly eur = eur;
  notes: Record<string, string> = {};

  constructor() {
    this.load();
  }

  load() {
    this.api.sellerQueue().subscribe(tickets => this.tickets.set(tickets));
  }

  decide(ticket: Ticket, decision: 'approve' | 'reject') {
    this.api.decide(ticket.ticket_id, decision, this.notes[ticket.ticket_id] ?? '').subscribe(updated =>
      this.tickets.update(all => all.map(t => (t.ticket_id === updated.ticket_id ? updated : t))));
  }

  /** Deterministic suggestion from the business rules; the rep decides. */
  recommendation(t: Ticket): string {
    const reasons = (t.payload.quote_reasons ?? []).join(' ');
    if (t.type === 'handoff') return 'Contact the buyer directly; this needs a person, not a price decision.';
    if (reasons.includes('prepayment')) return 'Approve as a prepayment order: send a pro-forma invoice before dispatch.';
    if (reasons.includes('exceeds available credit')) return 'Check with the credit team before approving, or offer partial delivery within the credit limit.';
    if (t.payload.requested_discount_pct) return 'Volume tiers already apply. Consider a project price only if the volume is recurring.';
    if (reasons.includes('above')) return 'Large order: confirm stock allocation and delivery schedule, then approve.';
    return 'Review the lines and approve or adjust.';
  }
}
