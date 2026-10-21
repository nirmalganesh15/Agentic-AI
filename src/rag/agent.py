from typing import Annotated

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.messages import AnyMessage, HumanMessage, ToolMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph, add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel

from rag.schema import ToolCallInfo
from rag.employee_data import EMPLOYEES, ROLE_HIERARCHY, HR_ROLES

load_dotenv()


def multiply(a: int, b: int) -> int:
    """Tool to multiply 2 number"""
    return a * b

def add(a: int, b: int)-> int:
    """Tool to add two numbers """
    return a + b

def get_roles() -> list:
    """Tool to get roles details """
    return ROLE_HIERARCHY

def get_employee_details(emp_id: str)->dict:
    """Tool to get employee details for given employee id"""
    emp_id = emp_id.strip().upper()
    if EMPLOYEES[emp_id] is None:
        return f"No employee found with id {emp_id}"
    return EMPLOYEES[emp_id]

tools = [multiply, add, get_roles, get_employee_details]
llm_with_tools = init_chat_model(model="claude-haiku-5-5", 
                                 output_config={"effort": "low"}).bind_tools(tools)


class AgentState(BaseModel):
    messages: Annotated[list[AnyMessage], add_messages]

sys_msg = SystemMessage(content="You are helpful assistance in doing arithmetic operations with tools given to you.")
def call_llm(state: AgentState) -> dict:
    """Node to call llm model with the conversation so far"""
    print(f"State before llm invoke{state.messages}")
    return {"messages": [llm_with_tools.invoke([sys_msg] + state.messages)]}


builder = StateGraph(AgentState)
builder.add_node("llm", call_llm)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "llm")
builder.add_conditional_edges("llm", tools_condition)
builder.add_edge("tools", "llm")

graph = builder.compile(checkpointer=InMemorySaver())


async def run_agent(question: str, thread_id: str) -> tuple[str, list[ToolCallInfo]]:
    """Run one conversation turn; returns the final answer and the tools used in this turn."""
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke({"messages": [HumanMessage(content=question)]}, config)
    messages = result["messages"]

    # Only look at messages produced in this turn (after the latest human message)
    last_human = max(i for i, m in enumerate(messages) if m.type == "human")
    turn = messages[last_human + 1:]

    tool_args = {tc["id"]: tc["args"] for m in turn if m.type == "ai" for tc in m.tool_calls}
    tools_used = [
        ToolCallInfo(name=m.name, args=tool_args.get(m.tool_call_id, {}), result=str(m.content))
        for m in turn
        if isinstance(m, ToolMessage)
    ]

    return messages[-1].text, tools_used
