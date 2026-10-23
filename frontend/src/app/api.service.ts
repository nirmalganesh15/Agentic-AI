import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Account {
  account_id: string;
  company: string;
  buyer: string;
  location: string;
  price_group: string;
  payment_terms: string;
  available_credit: number;
  sales_rep: string;
}

export interface TraceEvent {
  kind: 'router' | 'llm' | 'tool' | 'guard' | 'fallback' | 'action';
  name: string;
  status: 'ok' | 'error' | 'fallback' | 'blocked' | 'skipped';
  detail: string;
  latency_ms: number | null;
}

export interface ProductCard {
  sku: string;
  name: string;
  pack: string;
  category: string;
  unit_price: number | null;
  price_basis: string | null;
  stock: number | null;
  warehouse: string | null;
  lead_time_days: number | null;
}

export interface ActionLine {
  sku: string;
  name: string;
  quantity: number;
  unit_price: number;
  line_total: number;
  in_stock: boolean;
}

export interface ProposedAction {
  action_id: string;
  type: 'cart_add' | 'quote_request' | 'handoff';
  account_id: string;
  summary: string;
  payload: {
    lines?: ActionLine[];
    net_total?: number;
    shipping?: number;
    quote_reasons?: string[];
    reason?: string;
    requested_discount_pct?: number | null;
  };
  status: string;
}

export interface Verification {
  amounts_checked: number;
  unverified_amounts: string[];
  citations_checked: number;
  invalid_citations: string[];
  passed: boolean;
}

export interface AgentResponse {
  answer: string;
  thread_id: string;
  intents: string[];
  rationale: string;
  allowed_tools: string[];
  trace: TraceEvent[];
  products: ProductCard[];
  actions: ProposedAction[];
  verification: Verification | null;
  models_used: string[];
  fallbacks: string[];
  sources: { id: string; citation: string }[];
  latency_ms: number;
}

export interface Simulation {
  erp_down: boolean;
  llm_down: boolean;
}

export interface Cart {
  lines: ActionLine[];
  net_total: number;
  shipping: number;
  quote_reasons: string[];
}

export interface Ticket {
  ticket_id: string;
  type: 'quote_request' | 'handoff';
  account_id: string;
  company: string;
  sales_rep: string;
  summary: string;
  payload: ProposedAction['payload'];
  status: 'open' | 'approved' | 'rejected';
  created_at: string;
  decision_note: string | null;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  accounts(): Observable<Account[]> {
    return this.http.get<Account[]>('/api/accounts');
  }

  ask(question: string, accountId: string, threadId: string, simulate: Simulation): Observable<AgentResponse> {
    return this.http.post<AgentResponse>('/api/agent/chat', {
      question, account_id: accountId, thread_id: threadId, simulate,
    });
  }

  confirm(actionId: string, accountId: string): Observable<{ result: string; ticket?: Ticket; cart?: Cart }> {
    return this.http.post<{ result: string; ticket?: Ticket; cart?: Cart }>(
      `/api/actions/${actionId}/confirm`, { account_id: accountId });
  }

  dismiss(actionId: string, accountId: string): Observable<void> {
    return this.http.post<void>(`/api/actions/${actionId}/dismiss`, { account_id: accountId });
  }

  cart(accountId: string): Observable<Cart> {
    return this.http.get<Cart>(`/api/cart/${accountId}`);
  }

  sellerQueue(): Observable<Ticket[]> {
    return this.http.get<Ticket[]>('/api/seller/queue');
  }

  decide(ticketId: string, decision: 'approve' | 'reject', note: string): Observable<Ticket> {
    return this.http.post<Ticket>(`/api/seller/queue/${ticketId}/decision`, { decision, note });
  }
}
