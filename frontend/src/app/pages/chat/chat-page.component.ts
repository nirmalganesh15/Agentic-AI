import { Component, ElementRef, computed, effect, inject, signal, viewChild } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { Account, AgentResponse, ApiService, Cart, ProposedAction } from '../../api.service';
import { ActionCardComponent, ActionState } from '../../components/action-card.component';
import { ProductCardComponent } from '../../components/product-card.component';
import { TracePanelComponent } from '../../components/trace-panel.component';
import { Source, citedSources, eur, renderAnswer } from '../../format';

interface Message {
  role: 'user' | 'bot';
  text: string;
  html?: string;            // rendered once when the response arrives
  sources?: Source[];
  response?: AgentResponse;
  error?: boolean;
}

const SUGGESTIONS: Record<string, string[]> = {
  'ACC-1001': [
    "What's my price for 20 boxes of FAS-1001?",
    'Reorder the same items as my last order',
    'I need gloves for handling sheet metal',
    'What is the free shipping threshold?',
  ],
  'ACC-1002': [
    'Can you give me 25% off if I buy 100 boxes of FAS-1001?',
    'Are the FAS-1006 anchors in stock?',
    'I need PPE-2101 gloves',
    'How long is an approved quote valid?',
  ],
  'ACC-1003': [
    'Put 5 packs of MNT-6001 absorbent pads in my cart',
    'How much would 60 packs of safety glasses cost me?',
    'Can I return opened disposable gloves?',
    'Write me a poem about bolts',
  ],
};

function toBotMessage(res: AgentResponse): Message {
  const known = new Map(res.sources.map(s => [s.id, s.citation]));
  return { role: 'bot', text: res.answer, html: renderAnswer(res.answer, known), sources: citedSources(res.answer, known), response: res };
}

function errorText(err: HttpErrorResponse): string {
  if (err.status === 0) return "Can't reach the server. Check your connection and try again.";
  if (err.status === 429) return err.error?.detail ?? 'Too many requests. Please wait a moment and try again.';
  if (err.status === 422) return 'That question is too long. Please keep it under 1,000 characters.';
  return `Something went wrong (HTTP ${err.status}). Please try again.`;
}

@Component({
  selector: 'app-chat-page',
  imports: [FormsModule, ActionCardComponent, ProductCardComponent, TracePanelComponent],
  templateUrl: './chat-page.component.html',
  styleUrl: './chat-page.component.css',
})
export class ChatPageComponent {
  private api = inject(ApiService);
  private scroller = viewChild<ElementRef<HTMLElement>>('scroller');

  readonly accounts = signal<Account[]>([]);
  readonly accountId = signal('ACC-1001');
  readonly account = computed(() => this.accounts().find(a => a.account_id === this.accountId()));
  readonly suggestions = computed(() => SUGGESTIONS[this.accountId()] ?? []);

  readonly erpDown = signal(false);
  readonly llmDown = signal(false);

  question = '';
  readonly messages = signal<Message[]>([]);
  readonly loading = signal(false);
  readonly selected = signal<number | null>(null);   // index of the bot message shown in the trace panel
  readonly panelTab = signal<'trace' | 'cart'>('trace');
  readonly panelOpen = signal(false);                  // mobile only
  readonly cart = signal<Cart | null>(null);
  readonly actionStates = signal<Record<string, ActionState>>({});

  readonly selectedResponse = computed(() => {
    const i = this.selected();
    return i === null ? null : this.messages()[i]?.response ?? null;
  });
  readonly cartCount = computed(() => this.cart()?.lines.reduce((n, l) => n + l.quantity, 0) ?? 0);
  readonly eur = eur;

  // One conversation thread per account session; the backend scopes memory by account + thread
  private threadId = crypto.randomUUID();

  constructor() {
    this.api.accounts().subscribe(accounts => this.accounts.set(accounts));
    this.loadCart();

    effect(() => {
      this.messages();
      this.loading();
      const el = this.scroller()?.nativeElement;
      if (el) requestAnimationFrame(() => el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }));
    });
  }

  switchAccount(accountId: string) {
    this.accountId.set(accountId);
    this.newChat();
    this.loadCart();
  }

  newChat() {
    this.threadId = crypto.randomUUID();
    this.messages.set([]);
    this.selected.set(null);
    this.actionStates.set({});
  }

  ask(question: string) {
    this.question = question;
    this.send();
  }

  send() {
    const q = this.question.trim();
    if (!q || this.loading()) return;

    this.messages.update(m => [...m, { role: 'user', text: q }]);
    this.question = '';
    this.loading.set(true);

    this.api.ask(q, this.accountId(), this.threadId, { erp_down: this.erpDown(), llm_down: this.llmDown() })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: res => {
          this.messages.update(m => [...m, toBotMessage(res)]);
          this.selected.set(this.messages().length - 1);
          this.panelTab.set('trace');
        },
        error: (err: HttpErrorResponse) =>
          this.messages.update(m => [...m, { role: 'bot', text: errorText(err), error: true }]),
      });
  }

  onEnter(event: Event) {
    const key = event as KeyboardEvent;
    if (key.shiftKey || key.isComposing) return; // Shift+Enter = new line
    key.preventDefault();
    this.send();
  }

  showTrace(index: number) {
    this.selected.set(index);
    this.panelTab.set('trace');
    this.panelOpen.set(true);
  }

  stateOf(action: ProposedAction): ActionState {
    return this.actionStates()[action.action_id] ?? { status: 'pending' };
  }

  private setState(id: string, state: ActionState) {
    this.actionStates.update(s => ({ ...s, [id]: state }));
  }

  confirm(action: ProposedAction) {
    this.setState(action.action_id, { status: 'working' });
    this.api.confirm(action.action_id, this.accountId()).subscribe({
      next: res => {
        const message = res.result === 'added_to_cart'
          ? 'Added to cart'
          : `Sent to ${res.ticket?.sales_rep} (${res.ticket?.ticket_id})`;
        this.setState(action.action_id, { status: 'confirmed', message });
        this.loadCart();
      },
      error: (err: HttpErrorResponse) =>
        this.setState(action.action_id, { status: 'error', message: err.error?.detail ?? 'Could not confirm' }),
    });
  }

  dismiss(action: ProposedAction) {
    this.api.dismiss(action.action_id, this.accountId()).subscribe();
    this.setState(action.action_id, { status: 'dismissed' });
  }

  loadCart() {
    this.api.cart(this.accountId()).subscribe({ next: cart => this.cart.set(cart), error: () => this.cart.set(null) });
  }

  summary(res: AgentResponse): string {
    const tools = res.trace.filter(e => e.kind === 'tool').length;
    const parts = [res.intents.map(i => i.replace('_', ' ')).join(' + ') || 'declined', `${tools} tool ${tools === 1 ? 'call' : 'calls'}`];
    if (res.fallbacks.length) parts.push(`${res.fallbacks.length} fallback${res.fallbacks.length > 1 ? 's' : ''}`);
    parts.push(`${(res.latency_ms / 1000).toFixed(1)} s`);
    return parts.join(' · ');
  }
}
