import os

import chromadb
from langchain_chroma import Chroma
from langchain_classic.indexes import SQLRecordManager
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.document_loaders import TextLoader, UnstructuredFileLoader
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.indexing import index
from langchain_core.retrievers import BaseRetriever
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
import chardet

class Loader:
    loaderANSI = TextLoader(
        file_path="",
        encoding='gbk'
    )
    loader=UnstructuredFileLoader(
        file_path="",
        mode="elements"
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
        separators=["\n\n", "\n", "。", "！", "？","”"]
    )
    llm = ChatOllama(
        model="qwen2.5:7b",
        temperature=0.2,
        top_k=10,

    )
    recordmanager = SQLRecordManager(
        "chroma/my_index",
         db_url="sqlite:///chroma_db.sqlite"
    )#为每个文档块计算唯一哈希值（基于内容 + 元数据）去重
    recordmanager.create_schema()

    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    ensemble_retriever:BaseRetriever=None

    @staticmethod
    def get_vectorstore(collection_name:str):
        return Chroma(
            client=Loader.chroma_client,
            collection_name=collection_name,
            embedding_function=Loader.embeddings
        )


    @staticmethod
    def get_ensumble_retriever(collection_name:str):
        #根据 collection_name 动态构建 ensemble_retriever
        vectorstore=Loader.get_vectorstore(collection_name=collection_name)
        vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 8})
        all_data = vectorstore.get()
        if not all_data["documents"]:
            Loader.ensemble_retriever=vector_retriever
            return

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

        return EnsembleRetriever(
            retrievers=[bm25_retriever, vector_retriever],
            weights=[0.5, 0.5]
        )


    @staticmethod
    def load_and_split(path:str,collection_name:str)->int:
        ext = os.path.splitext(path)[1].lower()
        is_plain_text = ext in {".txt", ".md", ".py", ".json", ".csv", ".log"}

        loader=Loader.loaderANSI if Loader.check_encoding(path) else Loader.loader
        loader.file_path=path
        all_splits = loader.load_and_split(text_splitter=Loader.text_splitter)

        full_text=None
        if is_plain_text:
            with open(path, 'r',encoding='gbk' if Loader.check_encoding(path) else 'utf-8',errors='ignore' ) as f:
                full_text = f.read()

        current_pos=0

        for idx,split in enumerate(all_splits):
            split.metadata["source_path"]=os.path.abspath(path)
            split.metadata["filename"]=os.path.basename(path)
            split.metadata["chunk_index"]=idx

            content=split.page_content.strip()
            if not content:
                continue
            if is_plain_text and full_text:
                start_index=full_text.find(content[:50],current_pos)
                if start_index==-1:
                    # 找不到就退而求其次：别动 current_pos，粗略给个行号或直接跳过行号计算
                    split.metadata["start_line"] = None
                    split.metadata["end_line"] = None
                    continue

                #计算是第几个字符开始的 第几个字符结束的
                #start_index=split.metadata.get("start_index",0)
                end_index=start_index+len(content)

                current_pos=end_index
                #计算从开始字符到结束字符之间有多少个回车就是多少行
                #计算起始行和结束行
                split.metadata["start_line"]= full_text.count("\n",0,start_index)+1
                split.metadata["end_line"]= full_text.count("\n",0,end_index)+1

                split.metadata["chunk_id"]=f'{split.metadata["filename"]}_{split.metadata["start_line"]}'
            else:
                # docx / pdf 等：不算原文件“行号”，保留 loader 自带的页码等信息
                # UnstructuredFileLoader 通常会给 metadata["page_number"] 或类似字段
                split.metadata.setdefault("start_line", None)
                split.metadata.setdefault("end_line", None)
                split.metadata["chunk_id"] = (
                    f'{split.metadata["filename"]}_chunk_{idx}'
                )

            # 🔴 在这里加：过滤掉 dict / list 这种复杂 metadata，避免 Chroma 报错
            clean_meta = {}
            for k, v in (split.metadata or {}).items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    clean_meta[k] = v
                else:
                    # 对于复杂对象（dict/list/tuple等），要么丢弃，要么转成字符串
                    clean_meta[k] = str(v)
                    continue
            split.metadata = clean_meta

        index(
            all_splits,
            Loader.recordmanager,
            Loader.get_vectorstore(collection_name=collection_name),
            cleanup="incremental",# 增量更新，不重复的跳过
            source_id_key="source"#这是 Document 对象的元数据里存放文件路径或文件名的字段 用来分辨属于哪个文件
        )#去重入库

        #Loader.refresh_hybrid_retriever()
        Loader.get_ensumble_retriever(collection_name=collection_name)

        return len(all_splits)

    @staticmethod
    def check_encoding(path:str)->bool:
        with open(path, 'rb') as f:
            raw_data = f.read(10000)
            result=chardet.detect(raw_data)
            encoding = result['encoding']
            return True if encoding and encoding.lower()  in ('gb2312', 'gbk', 'ascii') else False
        #检查是不是gbk格式 如果是就用textloader读















