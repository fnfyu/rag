# 运行与降级

服务启动和 /health 检查不会加载 embedding、Cross-Encoder 或 Ollama。DATABASE_URL、模型名、存储目录和 CORS 都来自环境变量。缺少 embedding 配置时只有实际索引或检索请求返回清晰错误；缺少 reranker 时仍可用 RRF；上传任务状态目前保留在单进程内，多实例部署需要持久化 job table 或队列。
