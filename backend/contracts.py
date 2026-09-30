from dataclasses import dataclass, asdict


class WorkbenchError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Page:
    text: str
    page: int | None
    line_base: int = 1
    method: str = 'text_layer'
    confidence: float | None = None
    image_hash: str | None = None
    observations: tuple = ()


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    version_hash: str
    display_name: str
    text: str
    page: int | None
    line_start: int | None
    line_end: int | None
    extraction_method: str = 'text_layer'
    extraction_confidence: float | None = None
    page_image_hash: str | None = None
    retrieval_kind: str = 'dense'
    query_result: dict | None = None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Extraction:
    pages: list[Page]
    warnings: list[str]
    source_hash: str
