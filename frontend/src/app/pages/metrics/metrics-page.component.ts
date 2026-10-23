import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { catchError, map, of } from 'rxjs';
import { EvalReport, EvalService, Experiment, ExperimentMetric, SearchMode } from '../../eval.service';

type LoadState<T> = { status: 'loading' } | { status: 'error'; message: string } | { status: 'ready'; data: T };

const MODE_LABELS: Record<SearchMode, string> = {
  dense: 'Dense only',
  hybrid: 'Hybrid (dense + BM25)',
  hybrid_rerank: 'Hybrid + rerank',
};
const MODES: SearchMode[] = ['dense', 'hybrid', 'hybrid_rerank'];
const RANKING_METRICS = [
  { key: 'hit_at_1', label: 'Hit@1' },
  { key: 'hit_at_5', label: 'Hit@5' },
  { key: 'mrr', label: 'MRR' },
] as const;

const CATEGORY_LABELS: Record<string, string | undefined> = {
  product_search: 'Product search', pricing: 'Account pricing', availability: 'Stock & lead time',
  ordering: 'Ordering', quote: 'Quote / discount', handoff: 'Handoff to sales', policy: 'Trade policies',
  unanswerable: 'Unanswerable', off_topic: 'Off-topic', prompt_injection: 'Prompt injection', resilience: 'Outage fallbacks',
};

const CHECK_LABELS: Record<string, string | undefined> = {
  must_include: 'expected facts', must_not_include: 'forbidden content', prices_grounded: 'prices grounded',
  citations_valid: 'citations valid', expected_action: 'right action', no_unexpected_write: 'no unexpected write',
  expected_fallback: 'fallback triggered',
};

const OUTCOMES: Record<Experiment['outcome'], { label: string; tone: string; icon: string }> = {
  adopted: { label: 'Adopted', tone: 'good', icon: '✓' },
  kept: { label: 'Kept as safeguard', tone: 'accent', icon: '🛡' },
  eval_fix: { label: 'Eval fixed', tone: 'warning', icon: '⚙' },
  rejected: { label: 'Rejected', tone: 'critical', icon: '✕' },
};

const STRIP = { width: 640, left: 120, right: 16, laneA: 34, laneB: 74, axis: 102, height: 124 };

@Component({
  selector: 'app-metrics-page',
  imports: [DatePipe, DecimalPipe, KeyValuePipe],
  templateUrl: './metrics-page.component.html',
  styleUrl: './metrics-page.component.css',
})
export class MetricsPageComponent {
  private evals = inject(EvalService);

  readonly modes = MODES;
  readonly modeLabels = MODE_LABELS;
  readonly rankingMetrics = RANKING_METRICS;
  readonly checkLabels = CHECK_LABELS;
  readonly categoryLabels = CATEGORY_LABELS;
  readonly outcomes = OUTCOMES;
  readonly strip = STRIP;
  readonly corpora = [
    { key: 'catalog' as const, label: 'Product catalog' },
    { key: 'policies' as const, label: 'Trade policies' },
  ];

  readonly state = toSignal(
    this.evals.latest$.pipe(
      map(data => ({ status: 'ready', data }) as LoadState<EvalReport>),
      catchError(err => of({
        status: 'error',
        message: err.status === 404 ? 'No eval report has been published yet.' : 'Could not load the eval report.',
      } as LoadState<EvalReport>)),
    ),
    { initialValue: { status: 'loading' } as LoadState<EvalReport> },
  );
  readonly experiments = toSignal(this.evals.experiments$.pipe(catchError(() => of([] as Experiment[]))), {
    initialValue: [] as Experiment[],
  });

  readonly report = computed(() => {
    const s = this.state();
    return s.status === 'ready' ? s.data : null;
  });

  readonly phases = computed(() => {
    const groups = new Map<string, Experiment[]>();
    for (const e of this.experiments()) groups.set(e.phase, [...(groups.get(e.phase) ?? []), e]);
    return [...groups.entries()].map(([phase, items]) => ({ phase, items }));
  });

  readonly kpis = computed(() => {
    const s = this.report()?.agent?.summary;
    if (!s) return [];
    return [
      { label: 'Task success', value: this.pct(s.task_success, 1), note: 'judge correct and every check passed' },
      { label: 'Judge accuracy', value: this.pct(s.accuracy, 1), note: 'LLM judge vs reference answers' },
      { label: 'Router accuracy', value: this.pct(s.router_accuracy), note: 'right intents detected' },
      { label: 'Price grounding', value: this.pct(s.price_grounding), note: 'every € amount came from the ERP' },
      { label: 'Write safety', value: this.pct(s.write_safety), note: 'no cart or quote unless asked' },
      { label: 'Fallback success', value: this.pct(s.fallback_success), note: 'under simulated outages' },
      { label: 'Latency p50', value: `${(s.latency_ms_p50 / 1000).toFixed(1)}s`, note: `p95 ${(s.latency_ms_p95 / 1000).toFixed(1)}s · ${s.avg_tool_calls.toFixed(1)} tool calls avg` },
    ];
  });

  readonly categories = computed(() => {
    const s = this.report()?.agent?.summary;
    if (!s) return [];
    return Object.entries(s.success_by_category).map(([key, value]) => ({
      key, label: CATEGORY_LABELS[key] ?? key, value, count: s.cases_by_category[key] ?? 0,
    }));
  });

  // Case explorer
  readonly caseFilter = signal<'all' | 'issues'>('all');
  readonly cases = computed(() => {
    const all = this.report()?.agent?.cases ?? [];
    return this.caseFilter() === 'issues' ? all.filter(c => !c.success) : all;
  });
  readonly issueCount = computed(() => (this.report()?.agent?.cases ?? []).filter(c => !c.success).length);

  // Calibration strip: top policy reranker score per question vs the threshold
  readonly calibration = computed(() => {
    const abstention = this.report()?.retrieval.abstention;
    if (!abstention) return null;
    const scored = abstention.scores.filter(s => s.top_score !== null) as { id: string; category: string; answerable: boolean; top_score: number }[];
    const values = [...scored.map(s => s.top_score), abstention.threshold];
    const min = Math.floor(Math.min(...values) / 2) * 2;
    const max = Math.ceil(Math.max(...values) / 2) * 2;
    const x = (v: number) => STRIP.left + ((v - min) / (max - min)) * (STRIP.width - STRIP.left - STRIP.right);
    const ticks = [];
    for (let t = min; t <= max; t += 2) ticks.push({ value: t, x: x(t) });
    const lastX: Record<string, number> = {};
    const flip: Record<string, number> = {};
    const dots = [...scored].sort((a, b) => a.top_score - b.top_score).map(s => {
      const lane = s.answerable ? 'a' : 'b';
      const cx = x(s.top_score);
      const crowded = lastX[lane] !== undefined && cx - lastX[lane] < 11;
      flip[lane] = crowded ? (flip[lane] + 1) % 3 : 0;
      lastX[lane] = cx;
      return { ...s, cx, cy: (s.answerable ? STRIP.laneA : STRIP.laneB) + [0, -7, 7][flip[lane]],
               label: `${s.id} · ${CATEGORY_LABELS[s.category] ?? s.category} · score ${s.top_score.toFixed(2)}` };
    });
    return { threshold: abstention.threshold, thresholdX: x(abstention.threshold), ticks, dots,
             falseAbstention: abstention.false_abstention_rate, correctAbstention: abstention.correct_abstention_rate };
  });

  pct(value: number | null | undefined, digits = 0): string {
    return value == null ? '–' : `${(value * 100).toFixed(digits)}%`;
  }

  formatMetric(m: ExperimentMetric, value: number): string {
    if (m.format === 'pct') return this.pct(value, 1);
    if (m.format === 'ms') return `${Math.round(value)} ms`;
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }

  /** Signed change plus whether it's better or worse, so the badge never relies on color alone. */
  delta(m: ExperimentMetric): { text: string; tone: string } {
    const diff = m.after - m.before;
    if (Math.abs(diff) < 1e-9) return { text: '= no change', tone: 'neutral' };
    const better = (diff > 0) === m.higher_is_better;
    const sign = diff > 0 ? '+' : '−';
    const size = m.format === 'pct' ? `${Math.abs(diff * 100).toFixed(1)} pts`
      : m.format === 'ms' ? `${Math.round(Math.abs(diff))} ms` : Math.abs(diff).toFixed(3);
    return { text: `${better ? '✓' : '✕'} ${sign}${size} · ${better ? 'better' : 'worse'}`, tone: better ? 'good' : 'critical' };
  }

  gateLabel(metric: string): string {
    return metric.replace(/^agent\./, '').replace(/^retrieval\./, 'retrieval · ').replace('success_by_category.', 'success · ')
      .replace('hybrid_rerank.', '').replace(/_/g, ' ');
  }
}
