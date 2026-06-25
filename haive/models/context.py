from __future__ import annotations

from pydantic import BaseModel


class RelevantSymbol(BaseModel):
    qualified_name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    source: str


class RelevantFile(BaseModel):
    path: str
    reason: str


class BrokenReference(BaseModel):
    file_path: str
    symbol_name: str
    line_number: int


class ContextPack(BaseModel):
    relevant_files: list[RelevantFile]
    relevant_symbols: list[RelevantSymbol]
    impacted_files: list[str]
    broken_references: list[BrokenReference]
    symbol_source_token_estimate: int
