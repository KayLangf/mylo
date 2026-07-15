"""Chunking + embedding pipeline: reads source documents from
data/knowledge_base/, splits them into chunks tagged with metadata
(source document, section, date), embeds them, and loads them into
the local ChromaDB vector store. Run via `python src/ingest.py`.
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

KB_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge_base"
CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_db"
COLLECTION_NAME = "mylo_kb"
EMBEDDING_MODEL = "text-embedding-3-small"

HEADER_FIELD_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.*)$")


def parse_front_matter(front_matter_lines):
    """Extract doc title, **Key:** value fields, and any blockquote note
    from the lines preceding the `---` divider."""
    title = None
    fields = {}
    note_lines = []
    for line in front_matter_lines:
        stripped = line.strip()
        if title is None and stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        match = HEADER_FIELD_RE.match(stripped)
        if match:
            key = match.group(1).strip().lower()
            fields[key] = match.group(2).strip()
            continue
        if stripped.startswith(">"):
            note_lines.append(stripped.lstrip(">").strip())
    note = " ".join(note_lines).strip() or None
    return title, fields, note


def build_doc_metadata(filename, title, fields, note):
    """Map raw front-matter fields to the metadata schema required for
    every chunk. Only includes change_number/superseded when present."""
    metadata = {
        "source": filename,
        "source_url": fields.get("url", ""),
        "effective_date": fields.get("effective date") or fields.get("last verified") or "",
    }
    if "change number" in fields:
        metadata["change_number"] = fields["change number"]
    if note:
        if "SUPERSEDED" in note.upper():
            metadata["superseded"] = True
        elif "CURRENT AUTHORITATIVE" in note.upper():
            metadata["superseded"] = False
    return metadata, title


def split_into_chunks(body_lines, doc_title):
    """Structure-aware chunking: a new chunk starts at every ## or ###
    header. Content preceding the first ## header falls under doc_title."""
    chunks = []
    buffer = []
    current_h2 = doc_title
    current_h3 = None

    def flush():
        text = "".join(buffer).strip()
        if not text:
            return
        section_title = f"{current_h2} > {current_h3}" if current_h3 else current_h2
        heading_line = f"### {current_h3}" if current_h3 else f"## {current_h2}"
        chunk_text = f"{heading_line}\n\n{text}"
        chunks.append((section_title, chunk_text))

    for line in body_lines:
        stripped = line.rstrip("\n")
        if stripped.startswith("### "):
            flush()
            current_h3 = stripped[4:].strip()
            buffer = []
        elif stripped.startswith("## "):
            flush()
            current_h2 = stripped[3:].strip()
            current_h3 = None
            buffer = []
        else:
            buffer.append(line)
    flush()
    return chunks


def load_and_chunk_document(path):
    """Parse one markdown file into (chunk_text, metadata) pairs."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    divider_idx = next(
        (i for i, line in enumerate(lines) if line.strip() == "---"), None
    )
    if divider_idx is None:
        front_matter_lines, body_lines = lines, []
    else:
        front_matter_lines, body_lines = lines[:divider_idx], lines[divider_idx + 1 :]

    title, fields, note = parse_front_matter(front_matter_lines)
    doc_metadata, doc_title = build_doc_metadata(path.name, title, fields, note)

    warnings = []
    if not doc_metadata["source_url"]:
        warnings.append(f"{path.name}: missing source_url (no **URL:** line found)")
    if not doc_metadata["effective_date"]:
        warnings.append(
            f"{path.name}: missing effective_date "
            "(no **Effective date:** or **Last verified:** line found)"
        )

    chunk_records = []
    for section_title, chunk_text in split_into_chunks(body_lines, doc_title or path.stem):
        metadata = dict(doc_metadata)
        metadata["section_title"] = section_title
        chunk_records.append((chunk_text, metadata))

    return chunk_records, warnings


def embed_texts(texts):
    """Embed a list of texts using the OpenAI embeddings API. Reads the
    API key from OPENAI_API_KEY — never hardcoded."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def build_collection(chunk_texts, chunk_metadatas, chunk_ids):
    """(Re)create the ChromaDB collection and load embedded chunks into it."""
    import chromadb

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    embeddings = embed_texts(chunk_texts)
    collection.add(
        ids=chunk_ids,
        documents=chunk_texts,
        metadatas=chunk_metadatas,
        embeddings=embeddings,
    )
    return collection


def run_ingest():
    load_dotenv()

    doc_paths = sorted(KB_DIR.glob("*.md"))
    all_texts, all_metadatas, all_ids = [], [], []
    all_warnings = []

    for path in doc_paths:
        chunk_records, warnings = load_and_chunk_document(path)
        all_warnings.extend(warnings)
        for i, (chunk_text, metadata) in enumerate(chunk_records):
            all_texts.append(chunk_text)
            all_metadatas.append(metadata)
            all_ids.append(f"{path.stem}::{i}")

    build_collection(all_texts, all_metadatas, all_ids)

    print(f"Documents processed: {len(doc_paths)}")
    print(f"Chunks created: {len(all_texts)}")
    if all_warnings:
        print(f"Warnings ({len(all_warnings)}):")
        for warning in all_warnings:
            print(f"  - {warning}")
    else:
        print("No metadata warnings.")


if __name__ == "__main__":
    run_ingest()
