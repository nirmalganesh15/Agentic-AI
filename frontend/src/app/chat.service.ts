import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ChatResponse {
  answer: string;
}

export interface ToolCallInfo {
  name: string;
  args: Record<string, unknown>;
  result: string;
}

export interface AgentResponse {
  answer: string;
  thread_id: string;
  tools_used: ToolCallInfo[];
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private http = inject(HttpClient);
  private apiUrl = 'http://localhost:8000/chat';
  private agentUrl = 'http://localhost:8000/agent/chat';

  ask(question: string): Observable<ChatResponse> {
    return this.http.post<ChatResponse>(this.apiUrl, { question });
  }

  askAgent(question: string, threadId: string): Observable<AgentResponse> {
    return this.http.post<AgentResponse>(this.agentUrl, { question, thread_id: threadId });
  }
}
