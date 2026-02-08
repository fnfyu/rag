import os
import shutil

from fastapi import FastAPI, UploadFile, File, BackgroundTasks

from backend import Loader

app=FastAPI()

UPLOAD_DIR="./uploads"
os.makedirs(UPLOAD_DIR,exist_ok=True)

@app.post("/upload")
async def upload(
    background_tasks: BackgroundTasks,
        file: UploadFile = File(...)
):
    save_path=os.path.join(UPLOAD_DIR,file.filename)

    with open(save_path,mode="wb") as f:
        shutil.copyfileobj(file.file,f)#分块搬运文件

    background_tasks.add_task(analyze,save_path)

    return {
        "filename": file.filename,
        "status": "上传成功",
        "message": "文件已进入后台处理队列，解析完成后即可提问。"
    }

def analyze(path:str):
    print(f"开始后台解析：{path}")
    l=Loader.load_and_split(path)
    print(f"解析入库完成，新增 {l} 条数据")
