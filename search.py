import json
import uuid
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Body
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from starlette.responses import StreamingResponse

from backend import Loader
from utils import get_collection_name_from_db, insert_conversation_to_db, insert_message_to_db

router = APIRouter()

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

def build_sources(docs:List[Document])->List[Dict[str, Any]]:
    sources = []
    for i,doc in enumerate(docs):
        meta=doc.metadata or {}
        sources.append({
            'id':f'source_{i}',
            'filename': meta.get('filename'),
            'source_path': meta.get('source_path'),
            'start_line': meta.get('start_line'),
            'end_line': meta.get('end_line'),
            'chunk_id': meta.get('chunk_id'),
            "chunk_index": meta.get("chunk_index"),
            "page_number": meta.get("page_number") or meta.get("page"),  # pdf/docx 常见字段

        })
    return sources

@router.post('/chat/{conversation_id}')
async def chat_endpoint(
        conversation_id: str,
        body:dict=Body(...)
):
    messages=body.get('messages',[])

    if not messages:
        return StreamingResponse(
            iter([b""]),
            media_type="text/event-stream",
        )
    last_msg = messages[-1]
    parts = last_msg.get("parts") or []
    user_input = ""
    for part in reversed(parts):
        if part.get("type") == "text" and "text" in part:
            user_input = part.get("text")
            break

    if not user_input:
        return StreamingResponse(
            iter([b""]),
            media_type="text/event-stream",
        )
    # tmp=user_input.split("---")
    # user_input,conversation_id=tmp[0],tmp[1]
    if not conversation_id:
        return {"error": "缺少 conversation_id"}

    docs:List[Document]=await (Loader.get_ensumble_retriever(
        get_collection_name_from_db(conversation_id)).
                               ainvoke(user_input))

    context=format_docs(docs)
    sources=build_sources(docs)

    insert_message_to_db(conversation_id,role='user',content=user_input,source=None)
    insert_message_to_db(conversation_id,role='assistant',content=context,source=sources)
    # 相当于流水线
    rag_chain = (
            # {
            #     "context": Loader.ensemble_retriever | format_docs,  # 问题 → 检索器 → 文档列表 → 格式化字符串
            #     "query": RunnablePassthrough()
            # }
            prompt
            | llm
            | StrOutputParser()
    )
    async def event_stream():
        # 必须先发送一个 start 事件
        message_id = f"msg_{uuid.uuid4().hex}"
        yield f'data: {json.dumps({"type": "start", "messageId": message_id}, ensure_ascii=False)}\n\n'

        # 发一个source块
        yield f'data: {json.dumps({"type": "data-sources", "data": sources}, ensure_ascii=False)}\n\n'

        # 然后开始一个 text 块
        text_id = f"msg_{uuid.uuid4().hex}"
        yield f'data: {json.dumps({"type": "text-start", "id": text_id}, ensure_ascii=False)}\n\n'

        # 按 chunk 流式发送 text-delta
        async for chunk in rag_chain.astream({
            "context":context,
            "query":user_input
        }):
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





