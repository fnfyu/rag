import os
import shutil
import uuid

from fastapi import UploadFile, File, BackgroundTasks, APIRouter, Form

from backend import Loader
from utils import get_collection_name_from_db, save_file_record_to_db

router = APIRouter()

UPLOAD_DIR="./uploads"
os.makedirs(UPLOAD_DIR,exist_ok=True)

upload_status={}

@router.post("/upload")
async def upload(
    background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        conversation_id: str = Form(...)
):
    print(conversation_id)
    save_path=os.path.join(UPLOAD_DIR,file.filename)

    with open(save_path,mode="wb") as f:
        shutil.copyfileobj(file.file,f)#分块搬运文件

    upload_id=uuid.uuid4().hex
    upload_status[upload_id]='pending'
    background_tasks.add_task(analyze,save_path,upload_id,conversation_id,file.filename)

    return {
        "filename": file.filename,
        "status": "上传成功",
        "message": "文件已进入后台处理队列，解析完成后即可提问。",
        "upload_id":upload_id
    }

def analyze(path:str,upload_id:str,conversation_id:str,filename:str):
    print(f"开始后台解析：{path}")
    # 1. 从 PostgreSQL 查询这个对话的 collection_name
    # SELECT collection_name FROM conversations WHERE id = conversation_id
    collection_name=get_collection_name_from_db(conversation_id)

    l=Loader.load_and_split(path,collection_name)
    save_file_record_to_db(conversation_id,filename,path)

    upload_status[upload_id] = 'done'
    print(f"解析入库完成，新增 {l} 条数据")

@router.get("/upload/status")
async def get_upload_status(upload_id:str):
    return {"status":upload_status.get(upload_id,'pending')}
