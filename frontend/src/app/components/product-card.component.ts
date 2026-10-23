import { Component, computed, input } from '@angular/core';
import { ProductCard } from '../api.service';
import { eur } from '../format';

/** Product card rendered from structured tool output. Prices come from the ERP, never from LLM text. */
@Component({
  selector: 'app-product-card',
  template: `
    <article class="product">
      <div class="top">
        <span class="sku mono">{{ product().sku }}</span>
        <span class="category">{{ product().category }}</span>
      </div>
      <h4>{{ product().name }}</h4>
      <p class="pack">{{ product().pack }}</p>
      @if (product().unit_price !== null) {
        <p class="price">{{ price() }} <span class="per">/ {{ unit() }}</span></p>
        <p class="basis" [title]="product().price_basis ?? ''">{{ product().price_basis }}</p>
        @if ((product().stock ?? 0) > 0) {
          <span class="badge good">● {{ product().stock }} in stock · {{ product().warehouse }}</span>
        } @else {
          <span class="badge warning">◐ Backorder · {{ product().lead_time_days }} days</span>
        }
      } @else {
        <span class="badge critical">✕ Price unavailable (ERP offline)</span>
      }
    </article>
  `,
  styles: `
    .product {
      display: flex; flex-direction: column; gap: 2px; padding: var(--space-3); min-width: 0;
      border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--surface);
    }
    .top { display: flex; justify-content: space-between; gap: var(--space-2); }
    .sku { font-size: 12px; color: var(--accent-text); font-weight: 600; }
    .category { font-size: 11.5px; color: var(--text-muted); }
    h4 { margin: 2px 0 0; font-size: 13.5px; line-height: 1.35; }
    .pack { margin: 0; font-size: 12.5px; color: var(--text-muted); }
    .price { margin: 6px 0 0; font-size: 17px; font-weight: 650; font-variant-numeric: tabular-nums; }
    .per { font-size: 12px; font-weight: 400; color: var(--text-muted); }
    .basis { margin: 0 0 6px; font-size: 11.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .badge { align-self: flex-start; font-size: 11.5px; }
  `,
})
export class ProductCardComponent {
  readonly product = input.required<ProductCard>();
  readonly price = computed(() => eur(this.product().unit_price));
  readonly unit = computed(() => this.product().pack.replace(/^per /, ''));
}
