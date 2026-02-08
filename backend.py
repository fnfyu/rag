from langchain_classic.indexes import SQLRecordManager
from langchain_community.document_loaders import TextLoader, UnstructuredFileLoader
from langchain_core.indexing import index
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import chardet

class Loader:
    loaderANSI = TextLoader(
        file_path="",
        encoding='gbk'
    )
    loader=UnstructuredFileLoader(
        file_path="",
    )
    model_name = r"D:\fnfyu\projects\RAG\bge-small-zh-v1.5"
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={'device': 'cuda'},
        encode_kwargs={'normalize_embeddings': True}
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=["\n\n", "\n", "。", "！", "？"]
    )
    recordmanager = SQLRecordManager(
        "chroma/my_index",
         db_url="sqlite:///chroma_db.sqlite"
    )#为每个文档块计算唯一哈希值（基于内容 + 元数据）去重
    recordmanager.create_schema()

    @staticmethod
    def load_and_split(path:str)->int:
        loader=Loader.loaderANSI if Loader.check_encoding(path) else Loader.loader
        loader.file_path=path
        all_splits = loader.load_and_split(text_splitter=Loader.text_splitter)
        vectorstore=Chroma(
            persist_directory="./chroma_db",
            embedding_function=Loader.embeddings,
        )
        index(
            all_splits,
            Loader.recordmanager,
            vectorstore,
            cleanup="incremental",# 增量更新，不重复的跳过
            source_id_key="source"#这是 Document 对象的元数据里存放文件路径或文件名的字段 用来分辨属于哪个文件
        )#去重入库
        return len(all_splits)

    @staticmethod
    def check_encoding(path:str)->bool:
        with open(path, 'rb') as f:
            raw_data = f.read(10000)
            result=chardet.detect(raw_data)
            encoding = result['encoding']
            return True if encoding.lower() in ('gb2312', 'gbk', 'ascii') else False
        #检查是不是gbk格式 如果是就用textloader读















