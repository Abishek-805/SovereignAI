from dataclasses import dataclass, field
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[1]
EMBEDDING_REVISION = '5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get('SOVEREIGN_DATA_DIR', ROOT / 'data')).resolve())
    project_dir: Path | None = field(default_factory=lambda: Path(os.environ['SOVEREIGN_PROJECT_DIR']).resolve() if os.environ.get('SOVEREIGN_PROJECT_DIR') else None)
    model_dir: Path = ROOT / 'models' / 'bge-small-en-v1.5'
    model_url: str = 'http://127.0.0.1:8087'
    context: int = 24576
    output_tokens: int = 4096
    safety_tokens: int = 64
    max_file_bytes: int = 20 * 1024 * 1024
    max_pages: int = 200
    max_chunks: int = 20000
    chunk_tokens: int = 384
    overlap_tokens: int = 48

    @property
    def sources_dir(self) -> Path:
        override = os.environ.get('SOVEREIGN_KNOWLEDGE_DIR')
        if override:
            return Path(override).resolve()
        if self.data_dir == self.root / 'data':
            return Path.home() / 'Documents' / 'SovereignAI' / 'Knowledge'
        return self.data_dir / 'sources'
