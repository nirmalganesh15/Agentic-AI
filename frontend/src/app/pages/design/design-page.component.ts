import { Component, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, of } from 'rxjs';
import { ProductCard, ProposedAction } from '../../api.service';
import { ActionCardComponent } from '../../components/action-card.component';
import { ProductCardComponent } from '../../components/product-card.component';

interface ColorToken { light: string; dark: string; usage: string }
interface ValueToken { value: string; usage: string }
interface Tokens {
  color: Record<string, ColorToken>;
  radius: Record<string, ValueToken>;
  space: Record<string, ValueToken>;
  font: Record<string, ValueToken>;
}

const SAMPLE_PRODUCTS: ProductCard[] = [
  { sku: 'FAS-1001', name: 'Hex bolt M8x40, stainless steel A2', pack: 'box of 100', category: 'Fasteners', unit_price: 15.2, price_basis: 'contract price (fixed, no volume tiers)', stock: 420, warehouse: 'Rotterdam (NL)', lead_time_days: 3 },
  { sku: 'FAS-1006', name: 'Wedge anchor bolt M10x100 for concrete', pack: 'box of 25', category: 'Fasteners', unit_price: 27, price_basis: 'contract price (fixed, no volume tiers)', stock: 0, warehouse: 'Duisburg (DE)', lead_time_days: 10 },
  { sku: 'PPE-2003', name: 'Cut-resistant gloves level C, size 9', pack: 'pack of 12 pairs', category: 'PPE', unit_price: null, price_basis: null, stock: null, warehouse: null, lead_time_days: null },
];

const SAMPLE_ACTION: ProposedAction = {
  action_id: 'ACT-3F9A21C0', type: 'quote_request', account_id: 'ACC-1001', status: 'pending',
  summary: 'Quote request', payload: {
    lines: [{ sku: 'TLS-4001', name: 'Cordless drill driver 18 V', quantity: 400, unit_price: 156.49, line_total: 62596, in_stock: false }],
    net_total: 62596, quote_reasons: ['order total €62,596.00 exceeds available credit €6,800.00', 'order total above €10,000.00'],
  },
};

@Component({
  selector: 'app-design-page',
  imports: [ProductCardComponent, ActionCardComponent],
  templateUrl: './design-page.component.html',
  styleUrl: './design-page.component.css',
})
export class DesignPageComponent {
  private http = inject(HttpClient);
  readonly tokens = toSignal(this.http.get<Tokens>('/design-tokens.json').pipe(catchError(() => of(null))), { initialValue: null });

  readonly colors = computed(() => Object.entries(this.tokens()?.color ?? {}).map(([name, t]) => ({ name, ...t })));
  readonly spaces = computed(() => Object.entries(this.tokens()?.space ?? {}).map(([name, t]) => ({ name, ...t })));
  readonly radii = computed(() => Object.entries(this.tokens()?.radius ?? {}).map(([name, t]) => ({ name: name === 'default' ? '' : name, ...t })));
  readonly fonts = computed(() => Object.entries(this.tokens()?.font ?? {}).map(([name, t]) => ({ name, ...t })));
  readonly tokenCount = computed(() => {
    const t = this.tokens();
    return t ? Object.keys(t.color).length + Object.keys(t.space).length + Object.keys(t.radius).length + Object.keys(t.font).length : 0;
  });

  readonly sampleProducts = SAMPLE_PRODUCTS;
  readonly sampleAction = SAMPLE_ACTION;

  readonly principles = [
    { title: 'Tokens are data, with rules', body: 'Every token carries its light value, dark value and a usage rule in one JSON file. People read the rule on this page; AI design and code tools read the same rule from /design-tokens.json.' },
    { title: 'Generated, never hand-maintained', body: 'A build step turns the JSON into CSS variables for both themes. Changing a brand color is one edit; every component, chart and state updates without manual upkeep.' },
    { title: 'Agents emit data, components render it', body: 'The agent never writes HTML or styles. It returns structured products, actions and traces; these token-based components render them consistently and accessibly.' },
    { title: 'Status is never color alone', body: 'Good, warning and critical always pair color with an icon and a label, so meaning survives color blindness, dark mode and grayscale.' },
  ];
}
