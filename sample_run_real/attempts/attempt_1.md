# Introduction to RAG

## What is RAG?

RAG stands for Retrieval-Augmented Generation. Retrieval means finding useful information for a question. RAG is a way to let an AI look up facts before it answers.

First, a system finds relevant information from an outside source. Then, it gives that information to a Large Language Model (LLM). An LLM is an artificial intelligence program that reads and writes text. The LLM uses the found information to write the answer.

Think of RAG like an open-book exam. In an exam, a student can look at notes. RAG lets the model do the same thing.

## Why do we need RAG?

We need RAG because LLMs have limits.

First, an LLM learns from text up to a fixed date. This date is called the training cutoff. The model does not know facts after this date. So, its knowledge is old.

Second, an LLM has not seen private documents. For example, a company's internal files are not in its training data. The model cannot answer questions about these files.

Third, an LLM can produce a hallucination. A hallucination is a wrong answer that sounds right. The model makes up false facts.

RAG helps with these problems. It gives the LLM relevant facts at the time of the question. This helps with old knowledge, private data, and some hallucinations.

## How does RAG work?

RAG has two main stages. The first stage is preparing the knowledge. The second stage is answering each question.

### Stage 1: Preparing the knowledge

Indexing means preparing documents so the system can find useful parts later. This step happens before questions arrive.

1. Collect source documents. These can be web pages, books, or company files.
2. Split each document into smaller pieces called chunks. A chunk is a small piece of a document.
3. Turn each chunk into a list of numbers called an embedding. An embedding is numbers that show the meaning of a text.
4. Store the embeddings in a vector database. A vector database is a store that finds similar embeddings fast.

### Stage 2: Answering a question

When a user asks a question, the system follows these steps:

1. The user asks a question.
2. The system turns the question into an embedding.
3. The system searches the vector database. It looks for chunks with similar embeddings. This search is called retrieval.
4. The system builds a prompt. A prompt is the text sent to the LLM. It contains the question and the retrieved chunks.
5. The LLM reads the prompt. It writes an answer using the retrieved chunks.

RAG does not retrain or change the LLM. The model's internal settings, called weights, stay the same. The LLM only reads the retrieved text inside the prompt.

## Example: Asking about Company Leave Policy

Here is a worked example.

**The Setup:**
A company has a "Leave Policy" document. During indexing, the system split this document into chunks. One chunk says: "Employees get 10 days of paid leave per year." The system stored its embedding in the vector database.

**The Question:**
A new employee asks: "How many paid leave days do I get?"

**The RAG Steps:**

1. **Embedding:** The system turns the question into an embedding.
2. **Retrieval:** The system searches the database. It finds a close match. The match is the "10 days" chunk.
3. **Prompt:** The system builds a prompt. It adds the question and the "10 days" chunk.
4. **Generation:** The LLM reads the prompt. It writes: "You get 10 days of paid leave per year."

The LLM did not know this fact from its old training. It read the fact from the prompt.

## What RAG can and cannot do

RAG has benefits and limits.

**Benefits:**
*   It is easy to update. You update the documents. You do not need to train the LLM again.
*   It can use private documents. The LLM can read private files without training on them.
*   It can show sources. RAG can show which chunks an answer came from. Users can check the facts.
*   It reduces hallucinations. The LLM has relevant text to work from.

**Limits:**
*   It depends on retrieval. If the system finds the wrong chunks, the answer can be wrong.
*   It does not remove all mistakes. The LLM can still make mistakes.
*   It takes more time and cost. RAG adds extra steps. Each answer takes a little more time.
*   It has a size limit. Only a limited number of chunks can be sent to the LLM.

RAG is often easier than fine-tuning. Fine-tuning means training a model more on new data. Fine-tuning changes the model's weights. RAG does not change the weights.

## Summary

RAG stands for Retrieval-Augmented Generation. It helps LLMs answer questions better.

First, the system prepares documents. It splits them into chunks and stores their meanings in a vector database.

Then, when a user asks a question, the system finds the most useful chunks. It puts these chunks and the question into a prompt. The LLM reads this prompt and writes the answer.

RAG is like an open-book exam. It helps with old knowledge, private data, and made-up answers. But it is not perfect. If the system finds the wrong information, the answer will be wrong.
