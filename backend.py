from langchain_classic.indexes import SQLRecordManager
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.document_loaders import TextLoader, UnstructuredFileLoader
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
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

    vectorstore = Chroma(
        persist_directory="./chroma_db",
        embedding_function=embeddings,
    )
    ensemble_retriever=None

    @staticmethod
    def refresh_hybrid_retriever():
        vector_retriever = Loader.vectorstore.as_retriever(search_kwargs={"k": 8})
        all_data = Loader.vectorstore.get()
        all_docs = [
            Document(page_content=text, metadata=meta)
            for text, meta in zip(all_data["documents"], all_data["metadatas"])
        ]
        import jieba
        bm25_retriever = BM25Retriever.from_documents(
            all_docs,
            preprocess_func=jieba.lcut  # 中文分词器
        )
        bm25_retriever.k = 8

        Loader.ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, vector_retriever],
            weights=[0.4, 0.6]
        )


    @staticmethod
    def load_and_split(path:str)->int:
        loader=Loader.loaderANSI if Loader.check_encoding(path) else Loader.loader
        loader.file_path=path
        all_splits = loader.load_and_split(text_splitter=Loader.text_splitter)

        index(
            all_splits,
            Loader.recordmanager,
            Loader.vectorstore,
            cleanup="incremental",# 增量更新，不重复的跳过
            source_id_key="source"#这是 Document 对象的元数据里存放文件路径或文件名的字段 用来分辨属于哪个文件
        )#去重入库

        Loader.refresh_hybrid_retriever()

        return len(all_splits)

    @staticmethod
    def check_encoding(path:str)->bool:
        with open(path, 'rb') as f:
            raw_data = f.read(10000)
            result=chardet.detect(raw_data)
            encoding = result['encoding']
            return True if encoding and encoding.lower()  in ('gb2312', 'gbk', 'ascii') else False
        #检查是不是gbk格式 如果是就用textloader读















