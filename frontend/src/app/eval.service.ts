import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, shareReplay } from 'rxjs';

export type SearchMode = 'dense' | 'hybrid' | 'hybrid_rerank';

export interface RankingMetrics {
  cases: number;
  hit_at_1: number;
  hit_at_5: number;
  mrr: number;
  latency_ms_avg: number;
}

export interface AgentCase {
  id: string;
  category: string;
  account_id: string;
  question: string;
  simulate: Record<string, boolean>;
  expected_answer: string;
  answer: string;
  verdict: 'correct' | 'partially_correct' | 'incorrect';
  score: number;
  judge_reasoning: string;
  checks: Record<string, boolean>;
  success: boolean;
  intents: string[];
  router_correct: boolean;
  tools_called: string[];
  actions: string[];
  fallbacks: string[];
  latency_ms: number;
}

export interface AgentSummary {
  task_success: number;
  accuracy: number;
  checks_pass_rate: number;
  router_accuracy: number;
  price_grounding: number;
  citation_validity: number;
  action_accuracy: number | null;
  write_safety: number | null;
  fallback_success: number | null;
  guard_interventions: number;
  success_by_category: Record<string, number>;
  cases_by_category: Record<string, number>;
  avg_tool_calls: number;
  latency_ms_p50: number;
  latency_ms_p95: number;
}

export interface Gate {
  metric: string;
  minimum: number;
  value: number;
  passed: boolean;
}

export interface EvalReport {
  run_id: string;
  created_at: string;
  git_commit: string;
  variant: string;
  duration_s: number;
  passed: boolean;
  config: Record<string, string | number | boolean>;
  dataset: { cases: number };
  retrieval: {
    top_k: number;
    catalog: Record<SearchMode, RankingMetrics>;
    policies: Record<SearchMode, RankingMetrics>;
    abstention: {
      threshold: number;
      false_abstention_rate: number;
      correct_abstention_rate: number;
      scores: { id: string; category: string; answerable: boolean; top_score: number | null }[];
    };
  };
  agent?: { judge_model: string; summary: AgentSummary; cases: AgentCase[] };
  gates: Gate[];
}

export interface ExperimentMetric {
  name: string;
  before: number;
  after: number;
  format: 'pct' | 'ms' | 'num';
  higher_is_better: boolean;
}

export interface Experiment {
  id: string;
  phase: string;
  title: string;
  hypothesis: string;
  change: string;
  metrics: ExperimentMetric[];
  finding: string;
  decision: string;
  outcome: 'adopted' | 'kept' | 'eval_fix' | 'rejected';
  runs: string[];
}

@Injectable({ providedIn: 'root' })
export class EvalService {
  private http = inject(HttpClient);

  // Cached: reports only change on deploy, and several pages read them
  readonly latest$: Observable<EvalReport> = this.http.get<EvalReport>('/api/evals/latest').pipe(shareReplay(1));
  readonly experiments$: Observable<Experiment[]> = this.http.get<Experiment[]>('/api/experiments').pipe(shareReplay(1));
}
