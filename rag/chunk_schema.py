"""
Chunk schema for the BrightPeak policy RAG corpus.

This is the single source of truth for what a "chunk" looks like once it
leaves the ingestion pipeline and goes into the vector store's metadata
payload. See CHUNKING_STRATEGY.md for the reasoning behind each field.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class PolicyChunk:
    chunk_id: str             
    document_id: str          
    policy_type: str         
    section_id: str           
    section_title: str      
    text: str               
    last_reviewed_date: date
    version: str
    parent_section_id: str | None = None
    cross_refs: list[str] = field(default_factory=list)

    def to_metadata_payload(self) -> dict:
        """
        What gets stored in the vector DB's metadata payload store.
        Chroma's metadata only accepts primitive values (str/int/float/bool),
        so list and None values are serialized to strings here.
        """
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "policy_type": self.policy_type,
            "section_id": self.section_id,
            "section_title": self.section_title,
            "last_reviewed_date": self.last_reviewed_date.isoformat(),
            "version": self.version,
            "parent_section_id": self.parent_section_id or "",
            "cross_refs": ",".join(self.cross_refs),
        }

    def embedding_text(self) -> str:
        """What actually gets embedded: header prefix + body."""
        return f"[{self.document_id} — Section {self.section_id}]\n{self.section_title}\n{self.text}"