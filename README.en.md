# RAG Intelligent Conversation System

An intelligent conversation system based on Retrieval-Augmented Generation (RAG), supporting document upload, semantic search, and context-aware dialogue functionality.

## Features

- 📄 **Document Management**: Supports uploading documents in multiple formats, with automatic processing and vectorized storage
- 💬 **Intelligent Conversation**: Context-aware dialogue based on document content, supporting multi-turn conversations
- 🔍 **Semantic Search**: Hybrid retrieval mode combining vector similarity and keyword matching
- 📂 **Conversation Management**: Create, load, and view historical conversation records
- 🌐 **Modern Frontend**: Responsive interface built with Vue 3 + Vite

## Technology Stack

- **Backend**: Python, FastAPI, LangChain
- **Frontend**: Vue 3, Vite
- **Vector Database**: Chroma (or compatible vector database)
- **Database**: SQLite (default)

## Quick Start

### Prerequisites

- Python 3.8+
- Node.js 16+
- pip package manager

### Install Dependencies

1. Install backend dependencies:
```bash
pip install -r requirements.txt
```

2. Install frontend dependencies:
```bash
cd my-web
npm install
```

### Start Services

1. Start the backend service:
```bash
python starter.py
```
The backend service will be available at `http://localhost:8000`.

2. Start the frontend development server:
```bash
cd my-web
npm run dev
```
The frontend service will be available at `http://localhost:5173`.

## API Endpoints

### Conversation Management

- `POST /conversations/create` - Create a new conversation
- `GET /conversations/list` - Retrieve list of all conversations
- `GET /conversations/list/{conversation_id}` - Retrieve details of a specific conversation

### File Upload

- `POST /upload` - Upload a document file
- `GET /upload/status` - Check upload status

### Chat Functionality

- `POST /chat/{conversation_id}` - Send a message and receive a response

## Project Structure

```
rag/
├── backend.py           # Document loading and vector storage management
├── conversation.py      # Conversation management API
├── search.py            # Search and chat interface
├── upload.py            # File upload handling
├── utils.py             # Database utility functions
├── starter.py           # Application entry point
├── requirements.txt     # Python dependencies
├── my-web/              # Vue frontend project
│   ├── src/            # Frontend source code
│   ├── public/         # Static assets
│   └── package.json    # Frontend dependency configuration
└── .gitignore          # Git ignore configuration
```

## Usage Instructions

1. **Create a Conversation**: Create a new conversation session via the interface
2. **Upload Documents**: Use the upload feature to add documents; the system will automatically process and index them
3. **Start Chatting**: Engage in intelligent Q&A based on the uploaded document content
4. **View History**: Access and continue previous conversation records at any time

## License

This project is licensed under an open-source license. See the LICENSE file for details.