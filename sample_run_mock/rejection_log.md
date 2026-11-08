# Rejection log: Introduction to RAG

**Final status:** PASS (ships)  
**Attempts:** 2  **Shipped attempt:** 1

## Attempt 0: FAIL (3 checks)

> Deliberate test error injected: "RAG retrains the model on your documents every time you ask a question."

| Check | Why it failed | Evidence |
|---|---|---|
| `sentence_length` | 1 sentence(s) have more than 15 words. Split them. Worst: "RAG helps with all three problems because it gives the AI the right facts at exactly the …" (32 words) | RAG helps with all three problems because it gives the AI the right facts at exactly the right time before th… |
| `no_idioms` | Found phrases that are hard for the learner: "piece of cake". Use plain words. | Meena builds a helpbot for her school, and it is a piece of cake. |
| `claims_grounded` | 3 of 59 factual claims are not supported by the fact sheet: "RAG retrains the model on your documents every time you ask a question." → contradicted: The fact sheet says RAG does not retrain the LLM and does not remove all mistakes. / "RAG retrains the LLM on your documents each time." → contradicted: The fact sheet says RAG does not retrain the LLM and does not remove all mistakes. / "The LLM then remembers the facts for ever." → contradicted: The fact sheet says RAG does not retrain the LLM and does not remove all mistakes. | RAG retrains the model on your documents every time you ask a question. |

## Attempt 1: PASS

**Feedback the writer received:**
- `sentence_length`: 1 sentence(s) have more than 15 words. Split them. Worst: "RAG helps with all three problems because it gives the AI the right facts at exactly the …" (32 word…
- `no_idioms`: Found phrases that are hard for the learner: "piece of cake". Use plain words.
- `claims_grounded`: 3 of 59 factual claims are not supported by the fact sheet: "RAG retrains the model on your documents every time you ask a question." → contradicted: The fact …

**Writer says it changed:** - Split the very long sentence into two short ones.
- Removed the idiom.
- Replaced the wrong claim about retraining with the correct fact.

**What really changed (diff):** +3 / -5 lines

```diff
--- previous
+++ new
@@ -21 +21 @@
-RAG helps with all three problems because it gives the AI the right facts at exactly the right time before the AI writes any answer for the user who asked the question.
+RAG helps with all three problems. It gives the AI the right facts at the right time.
@@ -26,2 +25,0 @@
-
-RAG retrains the model on your documents every time you ask a question.
@@ -44 +42 @@
-RAG retrains the LLM on your documents each time. The LLM then remembers the facts for ever.
+RAG does not train the LLM again. The LLM only reads the facts in the prompt.
@@ -48 +46 @@
-Meena builds a helpbot for her school, and it is a piece of cake. Students ask it about exam dates and rules.
+Meena builds a helpbot for her school. Students ask it about exam dates and rules.
```
