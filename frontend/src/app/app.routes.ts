import { Routes } from '@angular/router';
import { ChatPageComponent } from './pages/chat/chat-page.component';

export const routes: Routes = [
  { path: '', component: ChatPageComponent, title: 'Buying assistant · Kestrel' },
  {
    path: 'seller',
    loadComponent: () => import('./pages/seller/seller-page.component').then(m => m.SellerPageComponent),
    title: 'Seller desk · Kestrel',
  },
  {
    path: 'how-it-works',
    loadComponent: () => import('./pages/how/how-page.component').then(m => m.HowPageComponent),
    title: 'How it works · Kestrel',
  },
  {
    path: 'metrics',
    loadComponent: () => import('./pages/metrics/metrics-page.component').then(m => m.MetricsPageComponent),
    title: 'Evals & experiments · Kestrel',
  },
  {
    path: 'design-system',
    loadComponent: () => import('./pages/design/design-page.component').then(m => m.DesignPageComponent),
    title: 'Design system · Kestrel',
  },
  { path: '**', redirectTo: '' },
];
