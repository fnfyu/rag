from fastapi import FastAPI
from pydantic import BaseModel
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama


app = FastAPI()

model_name=r"D:\fnfyu\projects\RAG\bge-small-zh-v1.5"

embeddings=HuggingFaceEmbeddings(
    model_name=model_name,
    model_kwargs={'device': 'cuda'},
    encode_kwargs={'normalize_embeddings': True}
)

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

vectorstore=Chroma(
    persist_directory="./chroma_db",
    embedding_function=embeddings
)

llm=ChatOllama(
    model="qwen2.5:7b",
    temperature=0.1
)

# query="叶文洁为什么背叛人类?"
#
# docs=vectorstore.similarity_search(query=query,k=3)
#
# for i,doc in enumerate(docs):
#     print(f"片段 {i + 1}:\n{doc.page_content}\n")

template='''
        你是一个专业的知识库助手,请根据以下提供的参考资料回答问题,如果资料里没有提及,你就说你不知道,别瞎编.
        参考资料:{context}。
        问题:{query}
        '''

prompt=ChatPromptTemplate.from_template(template)

retriever=vectorstore.as_retriever(search_kwargs={"k":8})

#相当于流水线
rag_chain=(
    {
        "context":retriever|format_docs,#问题 → 检索器 → 文档列表 → 格式化字符串
        "query":RunnablePassthrough()
    }
    |prompt
    |llm
    |StrOutputParser()
)

class ChatRequest(BaseModel):
    message:str

@app.post("/chat")
async def chat(request: ChatRequest):
    response = rag_chain.invoke(input=request.message)
    return {"response":response}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)



