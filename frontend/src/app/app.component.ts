import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <div class="shell">
      <header class="topbar">
        <a class="brand" routerLink="/">
          <span class="logo" aria-hidden="true">K</span>
          <span class="brand-text">
            <strong>Kestrel Supply</strong>
            <small>Agentic B2B commerce prototype</small>
          </span>
        </a>
        <nav aria-label="Main">
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Assistant</a>
          <a routerLink="/seller" routerLinkActive="active">Seller desk</a>
          <a routerLink="/how-it-works" routerLinkActive="active">How it works</a>
          <a routerLink="/metrics" routerLinkActive="active">Evals</a>
          <a routerLink="/design-system" routerLinkActive="active">Design system</a>
        </nav>
      </header>
      <main class="page">
        <router-outlet />
      </main>
    </div>
  `,
  styles: `
    .shell { height: 100dvh; display: flex; flex-direction: column; }
    .page { flex: 1; min-height: 0; overflow-y: auto; }
    .topbar {
      display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
      padding: 10px var(--space-5); background: var(--surface); border-bottom: 1px solid var(--border);
    }
    .brand { display: flex; align-items: center; gap: 10px; color: inherit; text-decoration: none; flex: none; }
    .logo {
      width: 34px; height: 34px; border-radius: var(--radius-md); display: grid; place-items: center;
      background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff; font-weight: 700;
    }
    .brand-text { display: flex; flex-direction: column; line-height: 1.2; }
    .brand-text strong { font-size: 15px; }
    .brand-text small { font-size: 12px; color: var(--text-muted); }
    nav { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: none; }
    nav a {
      padding: 7px 11px; border-radius: var(--radius-md); color: var(--text-secondary);
      text-decoration: none; font-size: 14px; font-weight: 500; white-space: nowrap;
    }
    nav a:hover { background: var(--surface-2); color: var(--text); }
    nav a.active { background: var(--accent-soft); color: var(--accent-text); }
    @media (max-width: 860px) {
      .topbar { flex-direction: column; align-items: stretch; gap: 6px; padding: 8px var(--space-4); }
      .brand-text small { display: none; }
    }
  `,
})
export class AppComponent {}
