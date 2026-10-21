from pydantic import BaseModel
from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model
from IPython.display import Image, display
from dotenv import load_dotenv

load_dotenv()

#Model creation
llm = init_chat_model(model="claude-haiku-5-5")

#Step:1 - state creation
class AgentState(BaseModel):
    name: str
    message: str = ""
    number_of_tools: int = 0

#Step:2 - Node Creation
def greetings(state: AgentState) -> AgentState:
    """Node to create greeting message and append it to existing state"""
    # state = {"message": f"{state.message} , Have a Great days ahead!! "}
    state.message = f"{state.name} , Have a Great days ahead!! "
    state.number_of_tools += 1
    return state

def nirmal_node(state: AgentState) -> AgentState:
    """Specialized node for Nirmal"""
    state.message = f"{state.message} All the best for the upcoming Job Interviews."
    state.number_of_tools += 1
    return state

def priya_node(state: AgentState) -> AgentState:
    """Specialized node for Priya"""
    state.message = f"{state.message} All the best for the upcoming GATE Exam."
    state.number_of_tools += 1
    return state

def decide_personal_node(state: AgentState):
    """Function to decide the personal node based on the name"""
    if state.name == "Nirmal":
        return "nirmal_node"
    elif state.name == "Priya":
        return "priya_node"
    else:
        return END



#Step:3 - Graph Creation
builder = StateGraph(AgentState)

#Step:4 - Add nodes to the graph
builder.add_node("greeter", greetings)
builder.add_node("nirmal_node", nirmal_node)
builder.add_node("priya_node", priya_node)

#Step:5 - Add edges
builder.add_edge(START,"greeter")
builder.add_conditional_edges("greeter", decide_personal_node)
builder.add_edge("nirmal_node", END)
builder.add_edge("priya_node", END)

#Step:6 - Compile graph
graph = builder.compile()

display(Image(graph.get_graph().draw_mermaid_png()))  # works in jupiter notebook

#Step:7 Invoke graph
result = graph.invoke({"name":"Meera"})

print(result)


