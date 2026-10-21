from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rag.agent import run_agent
from rag.chat import get_answer
from rag.schema import AgentRequest, AgentResponse, ChatRequest, ChatResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    answer = await get_answer(request.question)
    return ChatResponse(answer= answer)


@app.post("/agent/chat", response_model=AgentResponse)
async def agent_chat(request: AgentRequest):
    thread_id = request.thread_id or str(uuid4())
    answer, tools_used = await run_agent(request.question, thread_id)
    return AgentResponse(answer=answer, thread_id=thread_id, tools_used=tools_used)
