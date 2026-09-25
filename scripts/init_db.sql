-- Evidence RAG local development schema. Run after creating the PostgreSQL database.
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title VARCHAR(80) NOT NULL,
    collection_name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS uploaded_files (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    citation_validation JSONB NOT NULL DEFAULT '{}'::jsonb,
    retrieval_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Supports existing installations created by the original prototype.
ALTER TABLE uploaded_files ADD COLUMN IF NOT EXISTS chunk_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS citation_validation JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS retrieval_trace JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages (conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_uploaded_files_conversation
    ON uploaded_files (conversation_id, created_at DESC);
