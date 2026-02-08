from langchain_classic.indexes import SQLRecordManager
from langchain_community.document_loaders import TextLoader, UnstructuredFileLoader
from langchain_core.indexing import index
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

class Loader:
    def __init__(self):
        self.loaderTXT = TextLoader(
            file_path="",
            encoding='gbk'
        )
        self.loader=UnstructuredFileLoader(
            file_path="",
        )
        self.model_name = r"D:\fnfyu\projects\RAG\bge-small-zh-v1.5"
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.model_name,
            model_kwargs={'device': 'cuda'},
            encode_kwargs={'normalize_embeddings': True}
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "！", "？"]
        )
        self.recordmanager = SQLRecordManager(
            "chroma/my_index",
            db_url="sqlite:///chroma_db.sqlite"
        )#为每个文档块计算唯一哈希值（基于内容 + 元数据）去重
        self.recordmanager.create_schema()

    @staticmethod
    def load_and_split(self, path:str)->int:
        loader=self.loaderTXT if path.endswith(".txt") else self.loader
        loader.file_path=path
        all_splits = loader.load_and_split(text_splitter=self.text_splitter)
        vectorstore=Chroma(
            persist_directory="./chroma_db",
            embedding_function=self.embeddings,
        )
        index(
            all_splits,
            self.recordmanager,
            vectorstore,
            cleanup="incremental",# 增量更新，不重复的跳过
            source_id_key="source"#这是 Document 对象的元数据里存放文件路径或文件名的字段 用来分辨属于哪个文件
        )#去重入库
        return len(all_splits)














