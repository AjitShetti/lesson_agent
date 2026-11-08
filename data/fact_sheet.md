# Fact sheet: Retrieval-Augmented Generation (RAG)

Purpose: this is the ONLY source of truth for the evaluator. A claim in a lesson
is "supported" only if this sheet says the same thing.
Owner: the project author must verify every line against the sources below before use.
Sources to verify against:
- Lewis et al. (2020), "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", arXiv:2005.11401
- The public documentation of any major LLM provider or vector database on RAG

## Basics
- RAG stands for Retrieval-Augmented Generation.
- RAG is a method where a system first finds relevant information from an outside source, and then gives that information to a large language model (LLM) to help it write an answer.
- The term and the method were introduced in a 2020 research paper by Lewis and colleagues.
- An LLM is a computer program trained on a very large amount of text to read and write language.
- Retrieval means finding the pieces of information that are most relevant to a question.
- Generation means the LLM writing the answer.
- RAG is like an open-book exam: the model can look at reference material before it answers.

## Why RAG is needed
- An LLM learns from text collected up to a fixed date. This date is called the training cutoff.
- An LLM does not know events or facts that appeared after its training cutoff.
- An LLM has not seen private documents, such as a company's internal files, unless they were part of its training data.
- An LLM can produce a hallucination. A hallucination is an answer that sounds correct but is false or made up.
- RAG gives the LLM relevant and current facts at the time of the question. This helps with old knowledge, private data, and some hallucinations.

## How RAG works
- RAG has two stages: preparing the knowledge (indexing) and answering each question (retrieval and generation).
- Indexing step 1: collect the source documents, such as web pages, books, or company files.
- Indexing step 2: split each document into smaller pieces called chunks.
- Indexing step 3: turn each chunk into a list of numbers called an embedding. An embedding captures the meaning of the text, so chunks with similar meaning get similar numbers.
- Indexing step 4: store the embeddings in a vector database. A vector database is a store built to find similar embeddings quickly.
- Indexing is usually done before questions arrive, and it is repeated when documents change.
- Question step 1: the user asks a question.
- Question step 2: the system turns the question into an embedding.
- Question step 3: the system searches the vector database for the chunks whose embeddings are closest to the question. This search is called retrieval.
- Question step 4: the system builds a prompt. A prompt is the text sent to the LLM. The prompt contains the user's question and the retrieved chunks.
- Question step 5: the LLM reads the prompt and writes an answer, using the retrieved chunks as its source of facts.
- RAG does not change or retrain the LLM. The model's internal settings (weights) stay the same. The LLM only reads the retrieved text inside the prompt.

## Benefits
- To give the system new knowledge, you update the documents. You do not need to train the LLM again.
- RAG lets an LLM use private documents without training on them.
- RAG can show which chunks or documents an answer came from, so users can check the facts.
- RAG can reduce hallucinations, because the LLM has relevant text to work from.

## Limits
- RAG is only as good as its retrieval. If the system finds the wrong chunks, the answer can be wrong.
- RAG reduces hallucinations but does not remove them completely. The LLM can still make mistakes.
- RAG adds extra steps, so each answer takes a little more time and cost than asking the LLM alone.
- The prompt has a size limit, so only a limited number of chunks can be sent to the LLM.

## RAG compared with fine-tuning
- Fine-tuning means training an LLM further on new data, which changes the model's weights.
- RAG does not change the weights. It adds information at question time.
- RAG is often easier than fine-tuning when facts change often.
