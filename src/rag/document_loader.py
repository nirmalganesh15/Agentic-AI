import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.callbacks import UsageMetadataCallbackHandler
load_dotenv()


model = init_chat_model(model = "claude-haiku-5-5",
                        output_config ={"effort": "low"})

usage_cb = UsageMetadataCallbackHandler()
prompt = ChatPromptTemplate.from_messages([
    ("human", "{question}"),
])

chain = prompt | model 
parser =  JsonOutputParser()

chain_with_parser = prompt | model | JsonOutputParser()
# response = model.invoke("What is the captital of Newzeland")
raw_response = chain.invoke({"question": "List states in India in JSON format"})

for chunk in chain.stream({"question":"List districts in tamil nadu in JSON format"}):
    print(chunk.content, end="", flush=True)
response = parser.invoke(raw_response)
print(raw_response)
print(response)
print(raw_response.usage_metadata["total_tokens"])