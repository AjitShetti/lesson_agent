# Introduction to RAG

## What is RAG?

RAG stands for Retrieval-Augmented Generation. Retrieval means finding information. Augmented means made stronger. Generation means writing an answer. In simple words, RAG lets an AI look up facts before it answers.

Think of an exam where you can read your book. RAG gives the AI an open book.

An LLM is a Large Language Model. It is a computer program that reads and writes text. ChatGPT and Claude are examples of LLMs.

## Why do we need RAG?

An LLM learns from a large pile of text. This learning stops on a fixed date. After that date, the LLM knows nothing new.

This is the first problem. The LLM may give old answers. For example, it may not know last week's news.

The second problem is hallucination. A hallucination is when the AI gives a wrong answer that sounds right. The AI does not lie on purpose. It simply guesses a bad answer.

The third problem is private data. An LLM has never seen your school notes or your company files. It cannot answer questions about them.

RAG helps with all three problems. It gives the AI the right facts at the right time.

## How does RAG work?

RAG works in two parts. First, the system prepares the facts. Then, the system answers each question.

Part 1: Prepare the facts. This is done before any question comes.

1. Collect your documents. Examples are books, web pages, or company files.
2. Split each document into small pieces. Each piece is called a chunk. A chunk may be a few sentences long.
3. Turn each chunk into numbers. These numbers are called an embedding. An embedding shows the meaning of the text. Chunks with similar meaning get similar numbers.
4. Save all embeddings in a vector database. A vector database is a special store. It can find similar meanings very fast.

Part 2: Answer each question.

1. The user asks a question.
2. The system turns the question into an embedding.
3. The system searches the vector database. It finds the chunks with the closest meaning. This step is called retrieval.
4. The system writes a prompt. A prompt is the text that we send to the LLM. The prompt holds the question and the chunks.
5. The LLM reads the prompt and writes the answer. It uses the chunks as its facts.

RAG does not train the LLM again. The LLM only reads the facts in the prompt.

## Example: A school helpbot

Meena builds a helpbot for her school. Students ask it about exam dates and rules.

Without RAG, the bot guesses. It may give a wrong exam date.

With RAG, the bot first searches the school notices. A student asks, "When is the Maths exam?" The system finds a chunk that says, "The Maths exam is on 12 March." The system puts this chunk in the prompt. The LLM reads it and answers, "The Maths exam is on 12 March."

The answer is correct because the bot read the real notice. It did not guess.

## What RAG can and cannot do

RAG has many good points.

- The AI can use new facts. You only update the documents.
- The AI can use private files. You do not need to train it again.
- The AI can show its sources. Users can check the facts.

RAG also has limits.

- RAG is only as good as the chunks it finds. Wrong chunks give wrong answers.
- Each question takes a little more time. The system must search first.
- The AI can still make mistakes. RAG reduces them, but it does not remove them.

## Summary

- RAG lets an AI look up facts before it answers.
- The system finds the best chunks. Then it puts them in the prompt.
- The LLM answers using those chunks.
- RAG helps with old facts, wrong answers, and private data.
- RAG does not train the model again.
