# LangChain & LangGraph — Core Concepts Notes

> Quick-refresh cheat sheet. Organised by concept → **Import → Create → Use → Key params**.
> Versions used: `langchain >= 1.x`, `langgraph` (comes with langchain), `langchain-anthropic`.

---

## Table of Contents

1. [Model](#1-model)
2. [Tools](#2-tools)
3. [Agent (`create_agent`)](#3-agent-create_agent)
4. [Graph (LangGraph)](#4-graph-langgraph)
5. [Memory (Checkpointer)](#5-memory-checkpointer)
6. [Messages](#6-messages)
7. [Import Cheat Sheet](#7-import-cheat-sheet)

---

## 1. Model

### Import
```python
from langchain.chat_models import init_chat_model
```

### Create
```python
llm_model = init_chat_model(model="claude-haiku-5-5")
# provider is inferred from the name; or be explicit:
llm_model = init_chat_model(model="claude-haiku-5-5", model_provider="anthropic")
```

### Important parameters
| Param | Purpose |
|---|---|
| `model` | Model name, e.g. `"claude-haiku-5-5"` |
| `model_provider` | `"anthropic"`, `"openai"`, ... (optional if inferable) |
| `output_config={"effort": ...}` / `effort=...` | How much the model thinks/works: `"low"` → `"medium"` → `"high"` → `"xhigh"` → `"max"` |
| `temperature` | Randomness — ⚠️ **non-default values return a 400 error on recent Claude models** (Haiku 5.5, Sonnet 5.5, Opus 5.5, ...); use `effort` instead |
| `max_tokens` | Max output tokens |
| `timeout`, `max_retries` | Network behaviour |

### Effort (replaces `temperature` on recent models)
Controls thinking depth + token spend. Two equivalent ways to set it in LangChain:
```python
# 1. output_config dict (maps directly to the Anthropic API field)
llm_model = init_chat_model(
    model="claude-haiku-5-5",
    output_config={"effort": "low"},   # low = faster & cheaper, max = most thorough
)

# 2. shortcut param — langchain-anthropic writes it into output_config.effort
llm_model = init_chat_model(model="claude-haiku-5-5", effort="low")  # alias of reasoning_effort

# works the same when binding tools
llm_with_tools = init_chat_model(
    model="claude-haiku-5-5",
    output_config={"effort": "low"},
).bind_tools([multiply, add])

# override per call
llm_model.invoke("Hi", reasoning_effort="high")
```
| Effort | Use when |
|---|---|
| `"low"` | Chat, simple Q&A, classification, quick tool calls, subagents |
| `"medium"` | General tasks — **default on Haiku 5.5 & Opus 5.5** |
| `"high"` | Intelligence-sensitive work — **default on most other current models** |
| `"xhigh"` | Coding & long agentic tasks |
| `"max"` | Correctness matters more than cost |

> Default differs by model → set effort explicitly instead of relying on it.

### Invoke
```python
response = llm_model.invoke("Hello")                  # plain string
response = llm_model.invoke([HumanMessage("Hello")])  # list of messages
print(response.content)                               # AIMessage.content
```
- `.invoke()` → returns an `AIMessage`
- `.stream()` → yields chunks
- `.batch([...])` → multiple inputs in parallel

---

## 2. Tools

### Create a tool
A tool = a Python function with **type hints + docstring** (docstring is the description the LLM reads).

```python
from langchain.tools import tool

@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
```
> A plain function (no `@tool`) also works with `bind_tools` / `create_agent` — it is converted automatically.

### Tool for an **Agent**
Just pass the list — the agent handles calling & running tools.
```python
agent = create_agent(model=llm_model, tools=[multiply])
```

### Tool for a **Graph** (manual wiring)
1. Bind tools to the model → model can *request* a tool call
2. Add a `ToolNode` → actually *executes* the tool
3. Route with `tools_condition`

```python
from langgraph.prebuilt import ToolNode, tools_condition

llm_with_tool = llm_model.bind_tools([multiply])   # model now knows about tools

builder.add_node("tools", ToolNode([multiply]))
builder.add_conditional_edges("llm", tools_condition)  # → "tools" if tool_calls else END
builder.add_edge("tools", "llm")                       # loop back with tool result
```
> ⚠️ `bind_tools` alone does **not** run the tool — it only returns `response.tool_calls`.

---

## 3. Agent (`create_agent`)

### Import
```python
from langchain.agents import create_agent
```

### Create
```python
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model=llm_model,            # model object or string "anthropic:claude-haiku-5-5"
    tools=[multiply],
    system_prompt="You are a helpful assistant.",
    checkpointer=InMemorySaver(),  # memory (optional)
)
```

### Key arguments
| Arg | Purpose |
|---|---|
| `model` | Chat model instance or `"provider:model"` string |
| `tools` | List of tools / functions |
| `system_prompt` | System instructions: `str` or `SystemMessage` (see [Section 6](#6-messages)) |
| `checkpointer` | Enables memory across invokes |
| `response_format` | Structured output (Pydantic model) |
| `middleware` | Hooks (summarisation, HITL, etc.) |

### Invoke
```python
config = {"configurable": {"thread_id": "user1"}}
result = agent.invoke({"messages": [HumanMessage("What is 3 * 4?")]}, config)
print(result["messages"][-1].content)
```
> `create_agent` returns a compiled **LangGraph** graph → same `.invoke / .stream / .get_state` API.

---

## 4. Graph (LangGraph)

Flow: **State → Nodes → Builder → Edges → Compile → Invoke**

### Imports
```python
from langgraph.graph import StateGraph, START, END, add_messages
from typing import Annotated
from pydantic import BaseModel          # or TypedDict
from langchain.messages import AnyMessage
```

### 4.1 State creation
```python
class AgentState(BaseModel):
    messages: Annotated[list[AnyMessage], add_messages]
```
- `Annotated[..., add_messages]` = **reducer** → new messages are *appended*, not overwritten.
- Without a reducer, the returned value **replaces** the field.
- Can also use `TypedDict` or the built-in `MessagesState` ↓

#### Shortcut: `MessagesState` (built-in)
```python
from langgraph.graph import MessagesState   # note: MessagesState, not MessageState

# its definition in langgraph (graph/message.py):
# class MessagesState(TypedDict):
#     messages: Annotated[list[AnyMessage], add_messages]

builder = StateGraph(MessagesState)          # use it directly

class AgentState(MessagesState):             # or extend with extra fields
    user_id: str
```
| | Custom Pydantic state | `MessagesState` |
|---|---|---|
| Base type | `BaseModel` | `TypedDict` |
| Access in node | `state.messages` | `state["messages"]` |
| Validation | Yes (Pydantic) | No |

### 4.2 Node creation
A node = function that takes state, returns a **partial update**.
```python
def call_llm(state: AgentState):
    response = llm_with_tool.invoke(state.messages)
    return {"messages": [response]}   # reducer appends this
```
> With Pydantic state → access `state.messages`; with TypedDict → `state["messages"]`.

### 4.3 Graph builder
```python
builder = StateGraph(AgentState)
```

### 4.4 Add nodes & edges
```python
builder.add_node("llm", call_llm)

builder.add_edge(START, "llm")
builder.add_edge("llm", END)

# conditional routing
builder.add_conditional_edges("llm", router_fn)  # router_fn returns next node name
```

### 4.5 Compile
```python
graph = builder.compile()                              # no memory
graph = builder.compile(checkpointer=InMemorySaver())  # with memory
```

### 4.6 Invoke
```python
result = graph.invoke({"messages": [HumanMessage("hi")]}, config)
result["messages"]          # final state (dict)
```
- `graph.stream(input, config, stream_mode="values" | "updates" | "messages")`
- `graph.get_state(config).values` → current saved state for a thread

---

## 5. Memory (Checkpointer)

Short-term / conversation memory = **checkpointer** + **thread_id**.

### Import
```python
from langgraph.checkpoint.memory import InMemorySaver
```

### Where to attach
| Context | How |
|---|---|
| **Graph** | `graph = builder.compile(checkpointer=InMemorySaver())` |
| **Agent** | `create_agent(model, tools, checkpointer=InMemorySaver())` |

### Pass `configurable` on invoke (required!)
```python
config = {"configurable": {"thread_id": "user1"}}
graph.invoke({"messages": [HumanMessage("hi")]}, config)
```
- Same `thread_id` → conversation continues
- New `thread_id` → fresh conversation
- No need to manually keep a `conversation_history` list

### Read memory back
```python
state = graph.get_state(config)
for msg in state.values["messages"]:
    print(f"{msg.type}: {msg.content}")
```

> `InMemorySaver` is lost on restart. Persistent options: `SqliteSaver`, `PostgresSaver`.

### Deleting messages — `RemoveMessage`

Memory keeps growing → delete old messages from state.

```python
from langchain.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES
```

**How it works:** return `RemoveMessage(id=...)` from a node → the `add_messages` reducer **deletes** the message with that id (instead of appending).
- Needs the `add_messages` reducer on the field (custom state with `Annotated[..., add_messages]` or `MessagesState`)
- `RemoveMessage` takes only `id` — passing `content` raises `ValueError`
- Unknown id → `ValueError: Attempting to delete a message with an ID that doesn't exist`
- `RemoveMessage(id=REMOVE_ALL_MESSAGES)` → wipes the whole list

#### Example — keep only the last N messages
```python
N = 6

def trim_history(state: AgentState):
    """Node: delete everything except the last N messages."""
    old = state.messages[:-N]
    return {"messages": [RemoveMessage(id=m.id) for m in old]}

builder.add_node("trim", trim_history)
builder.add_edge(START, "trim")   # trim first, then call llm
builder.add_edge("trim", "llm")
```

#### Safer version — cut at a HumanMessage
A plain `[-N:]` cut can split a tool call (the `AIMessage` with `tool_calls` is deleted but its `ToolMessage` is kept) → Anthropic rejects the request. Start the kept window at a human message:
```python
def trim_history(state: AgentState):
    msgs = state.messages
    start = max(len(msgs) - N, 0)
    while start < len(msgs) and msgs[start].type != "human":  # move forward to a human msg
        start += 1
    return {"messages": [RemoveMessage(id=m.id) for m in msgs[:start]]}
```

#### Replace everything
```python
return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}
```

> `RemoveMessage` **permanently deletes** from the checkpoint. Only want to send fewer messages to the model but keep full history? Use `trim_messages` / `filter_messages` inside the LLM node ↓

### Trimming what the model sees — `trim_messages`

Returns a **new, shorter list** → pass it to the model. State/history is **not** changed.

```python
from langchain.messages import trim_messages   # also in langchain_core.messages
```

#### Key parameters
| Param | Purpose |
|---|---|
| `max_tokens` | **Required.** Max size of the kept messages (tokens — or message count if `token_counter=len`) |
| `token_counter` | **Required.** How to count: `"approximate"` (fast, recommended), the chat model itself (`llm_model`), or `len` (count **messages**) |
| `strategy` | `"last"` (default) = keep the most recent · `"first"` = keep the oldest |
| `allow_partial` | `False` (default) = drop a message that doesn't fit · `True` = keep **part** of it (last part for `"last"`, first part for `"first"`) |
| `start_on` | e.g. `"human"` → kept list starts at a human message (avoids splitting a tool call). Only with `strategy="last"` |
| `end_on` | Message type to end on |
| `include_system` | `True` → always keep the `SystemMessage` at index 0. Only with `strategy="last"` |
| `text_splitter` | How to split text when `allow_partial=True` (default: by newlines) |

#### Example — token budget inside the LLM node
```python
def call_llm(state: AgentState):
    recent = trim_messages(
        state.messages,
        max_tokens=1000,
        token_counter="approximate",
        strategy="last",        # keep newest
        start_on="human",       # valid start, no orphan ToolMessage
        allow_partial=False,    # don't cut messages in half
    )
    return {"messages": [llm_with_tools.invoke([SYSTEM, *recent])]}
```

#### Example — keep last N **messages** (safe version of `[-N:]`)
```python
recent = trim_messages(state.messages, max_tokens=6, token_counter=len,
                       strategy="last", start_on="human")
```

#### `allow_partial=True`
```python
trim_messages(msgs, max_tokens=200, token_counter="approximate",
              strategy="last", allow_partial=True)
# oldest message that doesn't fully fit → only its last lines are kept
```

### Filtering messages — `filter_messages`

Keep/drop messages by **type, name or id**. Also returns a new list.

```python
from langchain_core.messages import filter_messages   # ⚠️ not exported from langchain.messages

filter_messages(msgs, include_types=["human", "ai"])     # drop system/tool messages
filter_messages(msgs, exclude_types=[ToolMessage])       # classes work too
filter_messages(msgs, exclude_ids=["msg-123"])
filter_messages(msgs, exclude_tool_calls=True)           # drop tool calls + their results
```
| Param | Purpose |
|---|---|
| `include_types` / `exclude_types` | `"human"`, `"ai"`, `"system"`, `"tool"` or message classes |
| `include_names` / `exclude_names` | by `message.name` |
| `include_ids` / `exclude_ids` | by `message.id` |
| `exclude_tool_calls` | `True` = drop all AI messages with tool calls + all `ToolMessage`s · list of ids = drop just those calls and their results |

> ⚠️ To remove tool traffic, use `exclude_tool_calls=True`, not `exclude_types=[ToolMessage]`. The second keeps the AI tool-call messages but drops their results, which leaves an unmatched tool call.

#### Delete vs trim vs filter
| | Changes saved history? | Use for |
|---|---|---|
| `RemoveMessage` | ✅ Yes, permanently | Shrinking stored memory |
| `trim_messages` | ❌ No | Fit model context by token / message count |
| `filter_messages` | ❌ No | Drop messages by type / name / id |

---

## 6. Messages

```python
from langchain.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, AnyMessage
```
| Class | Role / `msg.type` |
|---|---|
| `SystemMessage` | `system` — instructions |
| `HumanMessage` | `human` — user input |
| `AIMessage` | `ai` — model output (`.content`, `.tool_calls`) |
| `ToolMessage` | `tool` — tool result |
| `AnyMessage` | type hint for any of the above |

### SystemMessage — instructions for the model

**Rule:** put it **first** in the message list. `langchain-anthropic` sends message[0] as Anthropic's `system` field.

#### a) Model — prepend to the messages
```python
from langchain.messages import SystemMessage, HumanMessage

response = llm_model.invoke([
    SystemMessage("You are a concise math tutor."),
    HumanMessage("What is 3 * 4?"),
])

# shorthand: (role, content) tuples also work
response = llm_model.invoke([("system", "You are a concise math tutor."), ("human", "3 * 4?")])
```

#### b) Agent — `system_prompt` argument
```python
agent = create_agent(
    model=llm_model,
    tools=[multiply],
    system_prompt="You are a concise math tutor.",                 # str
    # system_prompt=SystemMessage("You are a concise math tutor."), # or SystemMessage
)
agent.invoke({"messages": [HumanMessage("3 * 4?")]}, config)
```
- A `str` is converted to a `SystemMessage` automatically.
- The agent adds it in front of the messages **on every model call**, but does **not** save it in state. So it's not repeated in memory, and you don't pass it on invoke.

#### c) Graph — prepend inside the LLM node
```python
SYSTEM = SystemMessage("You are a concise math tutor.")

def call_llm(state: AgentState):
    response = llm_with_tools.invoke([SYSTEM, *state.messages])  # not stored in state
    return {"messages": [response]}
```
> ⚠️ Don't add a `SystemMessage` to the state on every invoke. With a checkpointer it builds up in history, and system messages that aren't next to each other raise `ValueError: Received multiple non-consecutive system messages` (except on models that accept system messages mid-conversation).

---

## 7. Import Cheat Sheet

| Need | Import |
|---|---|
| Chat model | `from langchain.chat_models import init_chat_model` |
| Messages | `from langchain.messages import HumanMessage, AIMessage, SystemMessage, AnyMessage` |
| Tool decorator | `from langchain.tools import tool` |
| Agent | `from langchain.agents import create_agent` |
| Graph | `from langgraph.graph import StateGraph, START, END, add_messages, MessagesState` |
| Prebuilt tool node | `from langgraph.prebuilt import ToolNode, tools_condition` |
| Memory | `from langgraph.checkpoint.memory import InMemorySaver` |
| Delete messages | `from langchain.messages import RemoveMessage` + `from langgraph.graph.message import REMOVE_ALL_MESSAGES` |
| Reducer type hint | `from typing import Annotated` |
| Env vars | `from dotenv import load_dotenv` |

---

<!-- Add new topics below under the matching category, or create a new numbered section. -->
