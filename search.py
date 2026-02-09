import json
import uuid
from contextlib import asynccontextmanager
from http.client import responses
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_ollama import ChatOllama
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from starlette.responses import StreamingResponse

from backend import Loader

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    Loader.refresh_hybrid_retriever()
    yield

app = FastAPI(lifespan=app_lifespan)

# model_name=r"D:\fnfyu\projects\RAG\bge-small-zh-v1.5"

# embeddings=HuggingFaceEmbeddings(
#     model_name=model_name,
#     model_kwargs={'device': 'cuda'},
#     encode_kwargs={'normalize_embeddings': True}
# )

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# vectorstore=Chroma(
#     persist_directory="./chroma_db",
#     embedding_function=embeddings
# )

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

# class ChatRequest(BaseModel):
#     message:str

# 1. 最内层：定义零件（parts）
class MessagePart(BaseModel):
    type: str
    text: str

# 2. 中间层：定义单条消息（message）
class Message(BaseModel):
    id: str
    role: str
    parts: List[MessagePart]  # 注意这里是 List

# 3. 最外层：定义整个请求体
class ChatRequest(BaseModel):
    id: str
    messages: List[Message]
    trigger: Optional[str] = None


@app.post("/chat")
async def chat_endpoint(request:ChatRequest):
    # 相当于流水线
    rag_chain = (
            {
                "context": Loader.ensemble_retriever | format_docs,  # 问题 → 检索器 → 文档列表 → 格式化字符串
                "query": RunnablePassthrough()
            }
            | prompt
            | llm
            | StrOutputParser()
    )
    user_input = request.messages[-1].parts[0].text
    async def event_stream():
        # 必须先发送一个 start 事件
        message_id = f"msg_{uuid.uuid4().hex}"
        yield f'data: {json.dumps({"type": "start", "messageId": message_id}, ensure_ascii=False)}\n\n'

        # 然后开始一个 text 块
        text_id = f"msg_{uuid.uuid4().hex}"
        yield f'data: {json.dumps({"type": "text-start", "id": text_id}, ensure_ascii=False)}\n\n'

        # 按 chunk 流式发送 text-delta
        async for chunk in rag_chain.astream(user_input):
            if not chunk:
                continue
            part = {
                "type": "text-delta",
                "id": text_id,
                "delta": chunk,
            }
            yield f"data: {json.dumps(part, ensure_ascii=False)}\n\n"

        # 文本结束
        yield f'data: {json.dumps({"type": "text-end", "id": text_id}, ensure_ascii=False)}\n\n'

        # 一条消息结束
        yield f'data: {json.dumps({"type": "finish"}, ensure_ascii=False)}\n\n'

        # 流结束标记
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 非常关键：告诉前端这是 Vercel AI UI 的数据流协议
            "X-Vercel-AI-UI-Message-Stream": "v1",
        },
    )
    #告诉服务器：“不要等函数跑完再发结果，只要 generate() 产生了一个 yield，就立刻把它发给客户端。”
    #media_type告诉浏览器：“我发给你的是标准流式协议的”。


# async def chat(request: ChatRequest):
#     response = rag_chain.invoke(input=request.message)
#
#     return {"response":response}




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)



