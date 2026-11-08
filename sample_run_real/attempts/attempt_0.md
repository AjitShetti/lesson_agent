# Introduction to RAG

## What is RAG?

RAG stands for Retrieval-Augmented Generation. Retrieval means finding useful information for a question. RAG is a way to let an AI look up facts before it answers.

First, a system finds relevant information from an outside source. Then, it gives that information to a Large Language Model (LLM). An LLM is a Large Language Model, a program that reads and writes text. The LLM uses the found information to write the answer.

Think of RAG like an open-book exam. In an open-book exam, a student can look at reference material before answering a question. RAG lets the model do the same thing.

## Why do we need RAG?

We need RAG because LLMs have limits.

First, an LLM learns from text collected up to a fixed date. This date is called the training cutoff. The model does not know events or facts that appeared after this date. So, its knowledge is old.

Second, an LLM has not seen private documents. For example, a company's internal files are not part of its training data. The model cannot answer questions about these private files.

Third, an LLM can produce a hallucination. A hallucination is a wrong answer that sounds right. The model makes up facts that are false.

RAG helps with these problems. It gives the LLM relevant and current facts at the time of the question. This helps with old knowledge, private data, and some hallucinations.

## How does RAG work?

RAG has two main stages. The first stage is preparing the knowledge. The second stage is answering each question.

RAG retrains the model on your documents every time you ask a question.

### Stage 1: Preparing the knowledge

Indexing means preparing documents so the system can find useful parts later. This step happens before questions arrive.

1. Collect source documents. These can be web pages, books, or company files.
2. Split each document into smaller pieces called chunks. A chunk is a small piece of a document.
3. Turn each chunk into a list of numbers called an embedding. An embedding is numbers that show the meaning of a text. Chunks with similar meaning get similar numbers.
4. Store the embeddings in a vector database. A vector database is a store that finds similar embeddings fast.

### Stage 2: Answering a question

When a user asks a question, the system follows these steps:

1. The user asks a question.
2. The system turns the question into an embedding.
3. The system searches the vector database. It looks for chunks whose embeddings are closest to the question. This search is called retrieval. Retrieval is finding the most useful information.
4. The system builds a prompt. A prompt is the text sent to the LLM. The prompt contains the user's question and the retrieved chunks.
5. The LLM reads the prompt. It writes an answer using the retrieved chunks as its source of facts.

RAG does not retrain or change the LLM. The model's internal settings, called weights, stay the same. Weights are the numbers inside a model that store what it learned. The LLM only reads the retrieved text inside the prompt.

## Example: Asking about Company Leave Policy

Here is a worked example.

**The Setup:**
A company has a "Leave Policy" document. During indexing, the system split this document into chunks. One chunk says: "Employees get 10 days of paid leave per year." The system turned this chunk into an embedding and stored it in the vector database.

**The Question:**
A new employee asks: "How many paid leave days do I get?"

**The RAG Steps:**

1. **Embedding the Question:** The system turns the question "How many paid leave days do I get?" into an embedding.
2. **Retrieval:** The system searches the vector database. It finds that the embedding for the question is very close to the embedding for the "10 days of paid leave" chunk.
3. **Building the Prompt:** The system creates a prompt. The text in the prompt is:
   *Context:* "Employees get 10 days of paid leave per year."
   *Question:* "How many paid leave days do I get?"
4. **Generation:** The LLM reads the prompt. It sees the context. It writes the answer: "You get 10 days of paid leave per year."

The LLM did not know this fact from its old training. It read the fact from the prompt.

## What RAG can and cannot do

RAG has benefits and limits.

**Benefits:**
*   It is easy to update. To give the system new knowledge, you update the documents. You do not need to train the LLM again.
*   It can use private documents. The LLM can read private files without training on them.
*   It can show sources. RAG can show which chunks or documents an answer came from. Users can check the facts.
*   It reduces hallucinations. The LLM has relevant text to work from.

**Limits:**
*   It depends on retrieval. If the system finds the wrong chunks, the answer can be wrong.
*   It does not remove all mistakes. The LLM can still make mistakes.
*   It takes more time and cost. RAG adds extra steps. Each answer takes a little more time than asking the LLM alone.
*   It has a size limit. The prompt has a size limit. Only a limited number of chunks can be sent to the LLM.

RAG is often easier than fine-tuning. Fine-tuning means training a model more on new data. Fine-tuning changes the model's weights. RAG does not change the weights. RAG adds information at question time.

## Summary

RAG stands for Retrieval-Augmented Generation. It helps LLMs answer questions better.

First, the system prepares documents. It splits them into chunks and stores their meanings in a vector database.

Then, when a user asks a question, the system finds the most useful chunks. It puts these chunks and the question into a prompt. The LLM reads this prompt and writes the answer.

RAG is like an open-book exam. It helps with old knowledge, private data, and made-up answers. But it is not perfect. If the system finds the wrong information, the answer will be wrong.
