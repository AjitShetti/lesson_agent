# RAG

RAG is a piece of cake once you look under the hood, and it is basically a retrieval pipeline that uses embeddings stored in a vector database so that the LLM can ground its generations in external context at inference time without any additional gradient updates.

In a nutshell, RAG retrains the model on your documents every time you ask a question, so hallucinations are completely removed and the answers are always correct, e.g. for private data, legal data, etc.

The chunking strategy and the embedding dimensionality matter a lot for the recall of the retriever, and the ANN index in the vector database is tuned with HNSW parameters which control the trade-off between latency and accuracy in production.

Overall RAG is the bottom line for every AI product.
