"""Vector search over the knowledge base. Given a query, retrieves the
most relevant chunks (with their source/section/date metadata) from
ChromaDB for the agent to ground its responses in. Read-only and
stateless — safe to share across concurrent sessions.
"""
