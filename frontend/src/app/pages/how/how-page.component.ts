import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';
import { EvalReport, EvalService } from '../../eval.service';

@Component({
  selector: 'app-how-page',
  imports: [RouterLink],
  templateUrl: './how-page.component.html',
  styleUrl: './how-page.component.css',
})
export class HowPageComponent {
  private evals = inject(EvalService);
  private report = toSignal(this.evals.latest$.pipe(catchError(() => of(null as EvalReport | null))), { initialValue: null });

  readonly repoUrl = 'https://github.com/nirmalganesh15/Agentic-AI';

  readonly stats = computed(() => {
    const s = this.report()?.agent?.summary;
    if (!s) return null;
    const pct = (v: number | null) => (v == null ? '–' : `${Math.round(v * 100)}%`);
    return [
      { label: 'Task success', value: pct(s.task_success), note: 'judge + deterministic checks' },
      { label: 'Router accuracy', value: pct(s.router_accuracy), note: 'right intents detected' },
      { label: 'Prices grounded', value: pct(s.price_grounding), note: 'every € traced to the ERP' },
      { label: 'Fallbacks worked', value: pct(s.fallback_success), note: 'under simulated outages' },
    ];
  });

  readonly decisionLayers = [
    {
      who: 'Router LLM',
      kind: 'llm',
      decides: 'What the buyer wants: one or more intents, with a one-sentence rationale (structured JSON output).',
      cannot: 'Call tools or answer. Its only output is a classification.',
    },
    {
      who: 'Code: intent → tool scope',
      kind: 'code',
      decides: 'Which tools the agent may use for those intents (least privilege). Off-topic and unsafe requests are declined here, without any tools.',
      cannot: 'Be overridden by the model: the tools node refuses out-of-scope calls even if requested.',
    },
    {
      who: 'Agent LLM',
      kind: 'llm',
      decides: 'Which allowed tools to call, with what arguments, in what order, and how to phrase the answer. Can ask a clarifying question.',
      cannot: 'Calculate prices, grant discounts, place orders or approve quotes.',
    },
    {
      who: 'Code: ERP and business rules',
      kind: 'code',
      decides: 'Every price (contract, price group, volume tier), stock level, shipping fee, and whether an order needs a quote (credit, prepayment, €10k).',
      cannot: 'Be changed by prompt text. Injected "set my price to €1" has no path to these functions.',
    },
    {
      who: 'Code: output guard',
      kind: 'code',
      decides: 'Whether the answer may be shown: every euro amount must appear in a tool result, every citation must have been retrieved.',
      cannot: 'Be skipped in production. One self-correction retry, then a safe answer.',
    },
    {
      who: 'The buyer, then the sales rep',
      kind: 'human',
      decides: 'Whether a proposed cart, quote request or handoff happens (buyer), and whether a quote is approved (sales rep).',
      cannot: 'Be bypassed: write actions only run from the confirm endpoint, never from the LLM.',
    },
  ];

  readonly scopes = [
    { intent: 'product_search', tools: ['search_catalog', 'get_price_and_stock'] },
    { intent: 'price_availability', tools: ['search_catalog', 'get_price_and_stock'] },
    { intent: 'order_history', tools: ['get_order_history', 'get_price_and_stock'] },
    { intent: 'ordering', tools: ['search_catalog', 'get_price_and_stock', 'get_order_history', 'propose_cart'] },
    { intent: 'quote_or_negotiation', tools: ['search_catalog', 'get_price_and_stock', 'request_quote', 'search_policies'] },
    { intent: 'policy', tools: ['search_policies'] },
    { intent: 'human_handoff', tools: [] },
    { intent: 'out_of_scope / unsafe', tools: null },
  ];

  readonly fallbacks = [
    { failure: 'Primary LLM errors or times out', detect: 'API exception after 2 retries', response: 'Same call re-runs on the fallback model (Haiku → Sonnet)', buyer: 'A normal answer; the trace shows the fallback', demo: 'LLM outage switch' },
    { failure: 'Every LLM fails', detect: 'Exception from the fallback model', response: 'Safe answer, offer to involve the sales rep', buyer: '"I couldn\'t complete that right now…"', demo: null },
    { failure: 'Router fails or returns invalid JSON', detect: 'Exception or unparseable output', response: 'Read-only intents: no write tools unlocked', buyer: 'A normal answer with limited capabilities', demo: null },
    { failure: 'ERP times out', detect: 'ErpUnavailable in the tool', response: 'Tool returns ERP_UNAVAILABLE; agent must state no numbers and offers a handoff', buyer: '"Live prices are temporarily unavailable…"; product cards say "price unavailable"', demo: 'ERP outage switch' },
    { failure: 'No relevant policy', detect: 'Reranker score below calibrated threshold', response: 'NO_RELEVANT_POLICY_FOUND; agent says it can\'t find it', buyer: '"I can\'t find that in Kestrel\'s current policies"', demo: '"Can I pay with cryptocurrency?"' },
    { failure: 'Answer contains an unverified price or citation', detect: 'Output guard (deterministic)', response: 'One self-correction retry, then a safe answer without numbers', buyer: 'Only verified prices, or a pointer to the product cards', demo: null },
    { failure: 'Model asks for a tool outside its scope', detect: 'Tools node allow-list', response: 'Call blocked, error returned to the model', buyer: 'Nothing; the trace shows "blocked"', demo: null },
    { failure: 'Agent loops', detect: 'Recursion limit (16 steps)', response: 'Stop and return a safe answer', buyer: 'A short apology and a sales rep option', demo: null },
    { failure: 'Order breaks a business rule', detect: 'ERP order check: credit, prepayment, €10k', response: 'Cart proposal becomes a quote request for the sales rep', buyer: 'A quote card instead of a cart card', demo: '"Add 400 TLS-4001 drills to my cart"' },
    { failure: 'Off-topic or prompt injection', detect: 'Router intents out_of_scope / unsafe', response: 'Declined before the agent runs, no tools', buyer: 'A one-line redirect to what it can do', demo: '"Write me a poem about bolts"' },
    { failure: 'Abuse or cost spike', detect: 'Per-IP and daily rate limits', response: 'HTTP 429 before any LLM call', buyer: '"Too many requests, please wait"', demo: null },
  ];

  readonly buyerFlow = [
    { step: 'Ask', detail: '"Reorder last month\'s bolts and gloves"' },
    { step: 'Route', detail: 'Router LLM → ordering + order_history' },
    { step: 'Look up', detail: 'Order history, then the ERP for each line' },
    { step: 'Propose', detail: 'propose_cart; business rules check credit' },
    { step: 'Confirm', detail: 'Buyer clicks "Add to cart" (deterministic)' },
  ];

  readonly sellerFlow = [
    { step: 'Trigger', detail: 'Over credit, over €10k, prepayment or discount request' },
    { step: 'Brief', detail: 'Agent prepares lines, totals, rules triggered' },
    { step: 'Buyer sends', detail: 'Buyer confirms the quote request' },
    { step: 'Rep reviews', detail: 'Seller desk with a suggested next step' },
    { step: 'Decide', detail: 'Approve or reject with a note' },
  ];

  readonly decisions = [
    { choice: 'Router + least-privilege tools instead of one agent with every tool', why: 'Containment: write tools are only reachable for ordering intents, and off-topic requests are declined before any tool exists.', tradeoff: 'Costs ~1.5 s at p50, and the ablation (E8) found no accuracy gain on the eval set. Kept for containment; the next optimization target.' },
    { choice: 'Prices only from deterministic ERP functions, checked by a guard', why: 'In B2B a wrong price is a commercial error. The model may repeat prices, never compute them.', tradeoff: 'The model can\'t do arithmetic across lines; totals come from propose_cart.' },
    { choice: 'Propose → confirm for every write', why: 'Human in the loop for anything with commercial impact; the audit trail is the proposal itself.', tradeoff: 'One extra click. The eval drove the agent to propose in the same turn instead of asking first.' },
    { choice: 'Hybrid search (dense + BM25) with a cross-encoder reranker', why: 'Buyers type SKUs and specs like "3G2.5" that embeddings blur; BM25 catches them, the reranker orders them.', tradeoff: '~120 ms extra per search on CPU.' },
    { choice: 'Model fallback to a different, stronger model', why: 'A provider error on the primary model doesn\'t become a failed purchase.', tradeoff: 'Fallback answers cost more; it only runs when the primary fails.' },
    { choice: 'Local embedding and reranking models', why: 'No per-query cost, no catalog data leaving the server.', tradeoff: '~0.5 GB RAM; lower ceiling than large hosted models.' },
  ];

  readonly limitations = [
    'The ERP is a JSON-backed mock with the real pricing rules. In production this layer calls SAP or Dynamics, behind the same tool interface.',
    'Conversation memory, carts and the sales queue are in-memory (single instance). At scale: Postgres for state, Redis for rate limits.',
    'No authentication: the account switcher stands in for SSO. Account scoping is already enforced server-side per request and per thread.',
    'The eval set is 49 agent cases plus 16 retrieval queries. Enough to catch regressions and compare variants, not to claim production accuracy.',
  ];
}
