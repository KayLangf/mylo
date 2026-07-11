"""Chunking + embedding pipeline: reads source documents from
data/knowledge_base/, splits them into chunks tagged with metadata
(source document, section, date), embeds them, and loads them into
the local ChromaDB vector store. Run via `python src/ingest.py`.
"""
