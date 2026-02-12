

# RAG 智能对话系统

基于检索增强生成（Retrieval-Augmented Generation）的智能对话系统，支持文档上传、语义搜索和上下文感知的对话功能。

## 功能特性

- 📄 **文档管理**：支持上传多种格式文档，自动处理和向量化存储
- 💬 **智能对话**：基于文档内容的上下文对话，支持多轮对话
- 🔍 **语义搜索**：混合检索模式，结合向量相似度和关键词匹配
- 📂 **对话管理**：创建、加载、查看历史对话记录
- 🌐 **现代化前端**：Vue 3 + Vite 构建的响应式界面

## 技术栈

- **后端**：Python, FastAPI, LangChain
- **前端**：Vue 3, Vite
- **向量数据库**：Chroma（或兼容的向量数据库）
- **数据库**：SQLite（默认）

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 16+
- pip 包管理器

### 安装依赖

1. 安装后端依赖：
```bash
pip install -r requirements.txt
```

2. 安装前端依赖：
```bash
cd my-web
npm install
```

### 启动服务

1. 启动后端服务：
```bash
python starter.py
```
后端服务将在 `http://localhost:8000` 启动。

2. 启动前端开发服务器：
```bash
cd my-web
npm run dev
```
前端服务将在 `http://localhost:5173` 启动。

## API 接口

### 对话管理

- `POST /conversations/create` - 创建新对话
- `GET /conversations/list` - 获取所有对话列表
- `GET /conversations/list/{conversation_id}` - 获取指定对话详情

### 文件上传

- `POST /upload` - 上传文档文件
- `GET /upload/status` - 查询上传状态

### 聊天功能

- `POST /chat/{conversation_id}` - 发送消息并获取回复

## 项目结构

```
rag/
├── backend.py           # 文档加载和向量存储管理
├── conversation.py      # 对话管理API
├── search.py            # 搜索和聊天接口
├── upload.py            # 文件上传处理
├── utils.py             # 数据库操作工具
├── starter.py           # 应用入口
├── requirements.txt     # Python依赖
├── my-web/              # Vue前端项目
│   ├── src/            # 前端源代码
│   ├── public/         # 静态资源
│   └── package.json    # 前端依赖配置
└── .gitignore          # Git忽略配置
```

## 使用说明

1. **创建对话**：在界面中创建新的对话会话
2. **上传文档**：通过上传功能添加文档资料，系统将自动处理并建立索引
3. **开始对话**：基于已上传的文档内容进行智能问答
4. **查看历史**：随时查看和继续之前的对话记录

## License

本项目遵循开源协议，具体信息请查看 LICENSE 文件。