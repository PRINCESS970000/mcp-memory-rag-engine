import re
from pathlib import Path
from datetime import date, datetime

from chunk_schema import PolicyChunk

POLICIES_DIR = Path(__file__).parent.parent / "policies"


FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---\n(.*)$', re.DOTALL)


def parse_frontmatter(raw_text: str) -> tuple[dict, str]:
    """
    Splits a policy .md file into (metadata_dict, body_text).
    metadata_dict has string values only -- callers convert types as needed.
    """
    match = FRONTMATTER_RE.match(raw_text)
    if not match:
        raise ValueError("File is missing a --- frontmatter block")

    frontmatter_block, body = match.groups()

    metadata = {}
    for line in frontmatter_block.strip().splitlines():
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()

    return metadata, body

HEADING_RE = re.compile(r'^(#{2,4})\s+(.*)$', re.MULTILINE)


def split_into_raw_sections(body: str) -> list[dict]:
    """
    Splits body text on ## / ### / #### headings.
    Returns a list of {"level": int, "heading_text": str, "content": str}
    in document order. "level" is 2 for ##, 3 for ###, 4 for ####.
    """
    matches = list(HEADING_RE.finditer(body))
    raw_sections = []

    for i, match in enumerate(matches):
        level = len(match.group(1))       # number of '#' characters
        heading_text = match.group(2).strip()

        start_of_content = match.end()
        end_of_content = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[start_of_content:end_of_content].strip()

        raw_sections.append({
            "level": level,
            "heading_text": heading_text,
            "content": content,
        })

    return raw_sections

SECTION_HEADING_RE = re.compile(r'^Section\s+([\d.a-z]+)\s*(?:—|-)\s*(.*)$')


def enrich_sections_with_ids(raw_sections: list[dict]) -> list[dict]:
    """
    Takes raw sections (from split_into_raw_sections) and adds:
      - section_id (e.g. "2.1")
      - section_title (e.g. "Standard Lapse")
      - parent_section_id (e.g. "2" for section "2.1", None for top-level sections)

    Parent tracking works by remembering the last section seen at each level.
    """
    enriched = []
    last_id_at_level: dict[int, str] = {}   # level -> most recent section_id at that level

    for raw in raw_sections:
        match = SECTION_HEADING_RE.match(raw["heading_text"])
        if not match:
            # Heading didn't follow the "Section X — Title" pattern; skip it
            continue

        section_id, section_title = match.groups()
        level = raw["level"]

        # Parent = the most recent section_id seen at the level just above this one
        parent_section_id = last_id_at_level.get(level - 1)

        last_id_at_level[level] = section_id

        enriched.append({
            "section_id": section_id,
            "section_title": section_title.strip(),
            "parent_section_id": parent_section_id,
            "content": raw["content"],
        })

    return enriched


CROSS_REF_RE = re.compile(
    r'see\s+(?:the\s+)?([A-Za-z][A-Za-z \-]+Policy)(?:,)?\s+Section\s+([\d.a-z]+)',
    re.IGNORECASE
)

# Maps a policy's human-readable name (as written in cross-reference text)
# to its document_id. Extend this whenever a new policy file is added.
POLICY_NAME_TO_DOC_ID = {
    "re-enrollment policy": "POL-RE-001",
    "certificate reissue policy": "POL-CR-002",
    "grade appeal policy": "POL-GA-003",
    "enrollment dispute policy": "POL-ED-004",
    "grading permissions policy": "POL-GP-005",
}


def extract_cross_refs(content: str, own_document_id: str) -> list[str]:
    """
    Finds phrases like "see Grade Appeal Policy, Section 3" inside a chunk's
    content and turns them into chunk_id references, e.g. "POL-GA-003_s3".
    Self-references (a policy citing its own sections) are skipped, since
    those don't need a retrieval hop.
    """
    refs = []
    for policy_name, section_id in CROSS_REF_RE.findall(content):
        doc_id = POLICY_NAME_TO_DOC_ID.get(policy_name.strip().lower())
        if doc_id is None or doc_id == own_document_id:
            continue
        refs.append(f"{doc_id}_s{section_id}")
    return refs

def load_policy_file(filepath: Path) -> list[PolicyChunk]:
    """Reads one policy .md file and returns its fully-built PolicyChunk objects."""
    raw_text = filepath.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(raw_text)

    raw_sections = split_into_raw_sections(body)
    enriched = enrich_sections_with_ids(raw_sections)

    document_id = metadata["document_id"]
    last_reviewed = datetime.strptime(metadata["last_reviewed_date"], "%Y-%m-%d").date()

    chunks = []
    for section in enriched:
        chunks.append(PolicyChunk(
            chunk_id=f"{document_id}_s{section['section_id']}",
            document_id=document_id,
            policy_type=metadata["policy_type"],
            section_id=section["section_id"],
            section_title=section["section_title"],
            text=section["content"],
            last_reviewed_date=last_reviewed,
            version=metadata["version"],
            parent_section_id=section["parent_section_id"],
            cross_refs=extract_cross_refs(section["content"], document_id),
        ))
    return chunks


def load_all_policies() -> list[PolicyChunk]:
    """Reads every .md file in policies/ and returns all chunks combined."""
    all_chunks = []
    for filepath in sorted(POLICIES_DIR.glob("*.md")):
        all_chunks.extend(load_policy_file(filepath))
    return all_chunks


if __name__ == "__main__":
    chunks = load_all_policies()
    print(f"Loaded {len(chunks)} chunks from {len(list(POLICIES_DIR.glob('*.md')))} files")
    for c in chunks:
        if c.cross_refs:
            print(f"  {c.chunk_id} -> {c.cross_refs}")