"""Environment-driven runtime configuration for the RAG service."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings deliberately avoid loading models or opening database connections."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Evidence RAG"
    app_environment: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
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

    # Evidence composition and bounded adaptive research.
    structure_indexing_enabled: bool = True
    context_token_budget: int = 6000
    context_max_documents: int = 8
    context_neighbor_chars: int = 240
    research_max_rounds: int = 3
    research_max_tasks: int = 4
    research_time_budget_seconds: float = 90.0
    research_planning_token_budget: int = 16000
    research_model_timeout_seconds: float = 25.0
    graph_enabled: bool = True
    graph_max_hops: int = 2
    graph_max_expansion_queries: int = 3
    claim_audit_enabled: bool = True
    claim_audit_max_claims: int = 12
    claim_audit_timeout_seconds: float = 45.0

    # Persistent research delivery and page/visual evidence.
    report_max_sections: int = 8
    report_worker_timeout_seconds: float = 1200.0
    asset_dir: Path = Path("data/assets")
    vision_model: str | None = None
    vision_indexing_enabled: bool = False
    pdf_page_render_enabled: bool = True
    vision_max_pages: int = 8
    vision_timeout_seconds: float = 60.0

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
        self.asset_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
