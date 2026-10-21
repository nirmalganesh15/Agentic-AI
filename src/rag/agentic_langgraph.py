from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, AnyMessage
from typing import Annotated
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

#Model initialization
llm_model = init_chat_model(model="claude-haiku-5-5")

def multiply(a: int, b :int)-> int:
    """Tool to multiply 2 number"""
    return a*b

llm_with_tool = llm_model.bind_tools([multiply])
#state Creation
class AgentState(BaseModel):
    messages: Annotated[list[AnyMessage], add_messages]

#Node creation
def call_llm(state: AgentState)->AgentState:
    """Node to call llm model with user message"""
    response = llm_with_tool.invoke(state.messages)
    print(f"AI: {response.content}")
    state.messages = [response]
    return state

builder = StateGraph(AgentState)

builder.add_node("llm",call_llm)
builder.add_node("tools", ToolNode([multiply]))
builder.add_edge(START, "llm")
builder.add_conditional_edges("llm", tools_condition)
builder.add_edge("tools", "llm")

graph = builder.compile(checkpointer=InMemorySaver())
# conversation_history = []
config = {"configurable": {"thread_id": "user1"}}
user_input = input("Enter: ")
while user_input != "exit":
    # conversation_history.append(HumanMessage(content=user_input))
    result = graph.invoke({"messages": [HumanMessage(content=user_input)]}, config)
    # conversation_history = result["messages"]
    user_input = input("Enter: ")

state = graph.get_state(config)

for msg in state.values["messages"]:
    print(f"{msg.type} : {msg.content}")

