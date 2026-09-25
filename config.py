"""Environment-driven runtime configuration for the RAG service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings deliberately avoid loading models or opening database connections."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Evidence RAG"
    app_environment: str = "development"
    database_url: str | None = None
    api_key: str | None = None
    embedding_model: str | None = None
    embedding_device: str = "cpu"
    ollama_model: str | None = None
    ollama_base_url: str | None = None
    chroma_path: Path = Path("data/chroma")
    upload_dir: Path = Path("data/uploads")
    record_manager_db: Path = Path("data/record_manager.sqlite")
    evaluation_dataset_path: Path = Path("evaluation/dataset.json")
    evaluation_report_path: Path = Path("evaluation/runs/latest.json")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_size_mb: int = 20
    candidate_k: int = 20
    final_context_k: int = 6
    rrf_k: int = 60
    reranker_model: str | None = None
    reranker_timeout_seconds: float = 20.0
    query_rewrite_enabled: bool = True
    query_rewrite_timeout_seconds: float = 8.0
    generation_timeout_seconds: float = 120.0
    parent_child_enabled: bool = True
    parent_chunk_size: int = 1800
    parent_chunk_overlap: int = 200
    child_chunk_size: int = 800
    child_chunk_overlap: int = 150
    max_extracted_chars: int = 2_000_000

    @property
    def record_manager_url(self) -> str:
        return f"sqlite:///{self.record_manager_db.resolve().as_posix()}"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def ensure_storage_directories(self) -> None:
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.record_manager_db.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
