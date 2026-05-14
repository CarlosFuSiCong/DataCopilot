# Context

This layer owns task context retrieval and context assembly.

Current modules:

- `rag_service`: builds `RAGContext` from dataset profile and retrieved docs.
- `retriever`: keyword and pgvector retriever selection.

This layer should avoid storing long-term user memory. Current context remains dataset/run scoped.
