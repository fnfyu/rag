from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from search import router as chat_router
from upload import router as upload_router
from conversation import router as conversation_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时先构建一次检索器
    #Loader.refresh_hybrid_retriever()
    yield

app=FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 挂载两个模块的路由
app.include_router(chat_router)    # /chat
app.include_router(upload_router)  # /upload, /upload/status
app.include_router(conversation_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)