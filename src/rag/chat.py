from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

load_dotenv()

model = init_chat_model(model = "claude-haiku-5-5")
prompt = ChatPromptTemplate.from_messages([
    ("human","{question}")
])
chain = prompt | model | StrOutputParser()

async def get_answer(question: str) -> str:
    return await chain.ainvoke({"question": question})