"""Vector search over the knowledge base. Given a query, retrieves the
most relevant chunks (with their source/section/date metadata) from
ChromaDB for the agent to ground its responses in. Query behavior is
read-only and stateless — safe to share across concurrent sessions. The
module does cache a shared ChromaDB client/collection handle (see
`_get_collection`), but that's shared read-only infrastructure, not
per-conversation state — it holds no session/history/facts data, so it
doesn't touch the Session Isolation design rule in CLAUDE.md.

Note: distances are squared L2, not cosine, despite embeddings being
unit-normalized (so rankings match what cosine would produce, but raw
values are ~2x cosine distance).
"""

import os
import threading
from pathlib import Path

from dotenv import load_dotenv

CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_db"
COLLECTION_NAME = "mylo_kb"
EMBEDDING_MODEL = "text-embedding-3-small"
# 8 rather than 5: SPEC.md Section 17's retrieval-context-scoping fix folds
# recent history into the query, but the relevant chunk can still land
# just outside a 5-wide window on borderline/diluted queries (confirmed
# via direct measurement: a reproduced miss at top_k=5 surfaced the
# target at rank 7 once top_k was widened). The surrounding fill-in
# chunks at ranks 6-8 were confirmed to be genuinely SNAP/FNS-relevant
# content, not noise, so widening does not trade retrieval precision for
# irrelevant filler.
DEFAULT_TOP_K = 8

_collection = None
_collection_lock = threading.Lock()


def embed_query(query):
    """Embed a single query string using the same OpenAI embedding model
    used at ingestion time, so query and chunk vectors live in the same
    space."""
    from openai import OpenAI

    load_dotenv()
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    return response.data[0].embedding


def _get_collection():
    """Return a shared handle to the mylo_kb collection, created once
    behind a lock (double-checked locking).

    chromadb.PersistentClient races when two threads instantiate it
    against the same on-disk path for the first time concurrently in one
    process — it raised AttributeError inside the Rust bindings
    (surfaced as "Could not connect to tenant default_tenant") when
    reproduced with two threads both calling this with no prior client
    yet created. See CLAUDE.md Learned Rules. Serializing first creation
    fixes it; querying the resulting collection is safe to do
    concurrently without the lock."""
    global _collection
    if _collection is None:
        with _collection_lock:
            if _collection is None:
                import chromadb

                client = chromadb.PersistentClient(path=str(_resolve_chroma_dir()))
                _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def _resolve_chroma_dir():
    """Return a writable path to the persisted collection. On Vercel the
    deployment bundle (including CHROMA_DIR) is read-only outside /tmp,
    and PersistentClient/SQLite need to open the store for write (WAL/
    journal files) even for read-only queries. The store is small
    (~2MB) and read-only in practice at request time, so a one-time copy
    into a writable temp dir per cold start is cheap and safe.

    Detects writability with a real write probe rather than checking an
    env var like Vercel's own `VERCEL=1` (opt-in per-project, easy to
    forget to enable) or `os.access` (reports POSIX permission bits,
    which can say "writable" even under a read-only bind mount — the
    exact case this needs to catch). This also means the same code path
    works unmodified on any other read-only-filesystem host, not just
    Vercel specifically."""
    probe = CHROMA_DIR / ".write_test"
    try:
        probe.touch()
        probe.unlink()
        return CHROMA_DIR
    except OSError:
        pass

    import shutil
    import tempfile

    tmp_dir = Path(tempfile.gettempdir()) / "mylo_chroma_db"
    if not tmp_dir.exists():
        shutil.copytree(CHROMA_DIR, tmp_dir)
    return tmp_dir


def _to_chunk(text, metadata, distance):
    """Assemble one retrieved chunk, carrying its full metadata forward
    unchanged. A missing `superseded` key (documents with no conflicting
    version) is treated as False rather than left absent or raising."""
    return {
        "text": text,
        "distance": distance,
        "source": metadata.get("source"),
        "section_title": metadata.get("section_title"),
        "effective_date": metadata.get("effective_date"),
        "superseded": bool(metadata.get("superseded", False)),
        "source_url": metadata.get("source_url"),
        "change_number": metadata.get("change_number"),
    }


def retrieve(query, top_k=DEFAULT_TOP_K):
    """Embed `query` and return the top_k most relevant knowledge base
    chunks, each carrying its full metadata (source, section_title,
    effective_date, superseded, ...).

    Superseded chunks are deliberately NOT filtered out here — both the
    current and superseded versions of a conflicting document (e.g. FNS
    360) may be retrieved when semantically relevant. Reconciling which
    figure to use happens in the agent's system prompt, not here. See
    SPEC.md Section 12.
    """
    collection = _get_collection()
    query_embedding = embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )

    texts = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    return [
        _to_chunk(text, metadata, distance)
        for text, metadata, distance in zip(texts, metadatas, distances)
    ]
