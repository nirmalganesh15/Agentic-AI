import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ChatService, ToolCallInfo } from './chat.service';

interface Message {
  role: 'user' | 'bot';
  text: string;
  tools?: ToolCallInfo[];
}

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})
export class AppComponent {
  private chatService = inject(ChatService);

  question = '';
  messages = signal<Message[]>([]);
  loading = signal(false);

  // One thread per conversation; the backend keeps its history under this id
  private threadId = crypto.randomUUID();

  send() {
    const q = this.question.trim();
    if (!q || this.loading()) return;

    this.messages.update(m => [...m, { role: 'user', text: q }]);
    this.question = '';
    this.loading.set(true);

    this.chatService.askAgent(q, this.threadId).subscribe({
      next: res => {
        this.messages.update(m => [...m, { role: 'bot', text: res.answer, tools: res.tools_used }]);
        this.loading.set(false);
      },
      error: () => {
        this.messages.update(m => [...m, { role: 'bot', text: 'Error: could not reach the API.' }]);
        this.loading.set(false);
      }
    });
  }

  newChat() {
    this.threadId = crypto.randomUUID();
    this.messages.set([]);
  }

  formatArgs(args: Record<string, unknown>): string {
    return Object.entries(args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ');
  }
}
