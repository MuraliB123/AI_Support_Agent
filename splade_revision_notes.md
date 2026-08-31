# SPLADE — Revision Notes

## 1. What is SPLADE?

**SPLADE = Sparse Lexical and Expansion Model**

SPLADE is a neural information-retrieval model that uses a BERT-style language model to produce **sparse, vocabulary-level representations**.

Core idea:

> Use BERT's contextual understanding to learn which vocabulary terms are important, while keeping the representation sparse enough to use a classical **inverted index**.

SPLADE combines:

- Neural semantic understanding
- Vocabulary expansion
- Sparse representations
- Inverted-index retrieval

---

## 2. Why SPLADE?

### Classical BM25

BM25 is lexical:

```text
Query:     "myocardial infarction"
Document:  "heart attack"
```

There may be little or no exact lexical overlap.

This is the **vocabulary mismatch problem**.

### Dense retrieval

Dense models encode text into dense vectors:

```text
Query    → [0.12, -0.31, 0.77, ...]
Document → [0.11, -0.29, 0.75, ...]
```

Semantic similarity is strong, but retrieval generally requires an ANN/vector index such as HNSW.

### SPLADE's goal

Get:

```text
BM25-like:
- sparse
- inverted index
- efficient lexical retrieval
```

while also getting:

```text
BERT-like:
- contextual understanding
- semantic expansion
```

---

# 3. SPLADE's representation

Suppose BERT has a vocabulary of:

\[
|V| = 30,522
\]

A SPLADE representation is therefore conceptually:

\[
w \in \mathbb{R}^{30,522}
\]

but **most values are zero**.

Example:

```text
heart        → 1.8
attack       → 1.5
cardiac      → 0.9
infarction   → 1.2
treatment    → 2.0
therapy      → 0.8
```

So SPLADE is:

> **High-dimensional but sparse**

This is different from a typical dense embedding such as a 768-dimensional vector.

---

# 4. Where do the vocabulary dimensions come from?

For an input sequence:

\[
t=(t_1,\ldots,t_N)
\]

BERT produces contextual representations:

\[
h_1,\ldots,h_N
\]

For each input token representation \(h_i\), SPLADE scores every vocabulary term \(j\).

Conceptually:

\[
w_{ij}
=
\text{transform}(h_i)^T E_j+b_j
\]

where:

- \(h_i\) = contextual representation of input token \(i\)
- \(E_j\) = embedding of vocabulary term \(j\)
- \(b_j\) = vocabulary-term bias
- `transform` = transformation used before vocabulary prediction

This uses the machinery of BERT's **Masked Language Model (MLM) prediction layer**.

---

# 5. The expansion mechanism

This is one of the most important SPLADE ideas.

Input:

```text
"The patient suffered a heart attack."
```

The final sparse representation might activate:

```text
heart
attack
cardiac
infarction
myocardial
treatment
...
```

Even if:

```text
infarction
myocardial
```

do not literally occur in the input.

Therefore SPLADE performs **learned vocabulary expansion**.

Important:

> SPLADE does NOT generate expanded text first.

Instead, it directly assigns weights to vocabulary dimensions.

So:

```text
Text
 ↓
BERT
 ↓
vocabulary scores
 ↓
sparse weighted vector
```

---

# 6. ReLU + log transformation

SPLADE transforms vocabulary scores using:

\[
\log(1+\operatorname{ReLU}(w_{ij}))
\]

### ReLU

\[
\operatorname{ReLU}(x)=\max(0,x)
\]

Negative scores become zero.

### Log saturation

\[
\log(1+x)
\]

compresses large values.

Example:

```text
raw score      log(1 + score)

1              0.69
10             2.40
100            4.62
1000           6.91
```

This prevents very large activations from dominating excessively.

---

# 7. Pooling over input tokens

After transforming each token's vocabulary scores, SPLADE aggregates them into one vocabulary vector.

## Original SPLADE: SUM pooling

\[
w_j
=
\sum_{i\in t}
\log(1+\operatorname{ReLU}(w_{ij}))
\]

For vocabulary term \(j\), evidence from all input tokens is added.

---

## SPLADE-max: MAX pooling

SPLADE-max instead uses:

\[
w_j
=
\max_{i\in t}
\log(1+\operatorname{ReLU}(w_{ij}))
\]

Interpretation:

> For each vocabulary term, keep the strongest evidence produced by any input token.

The paper reports that this simple change improves retrieval effectiveness.

---

# 8. Why sparsity is necessary

Without sparsity, the model could activate thousands of vocabulary terms.

For example:

```text
30,522 dimensions
        ↓
10,000 active terms
        ↓
huge inverted index
        ↓
expensive retrieval
```

Instead, we want something more like:

```text
30,522 dimensions
        ↓
50 active terms
        ↓
small sparse representation
        ↓
efficient inverted index
```

Sparsity is therefore not just a mathematical property.

It is a **systems requirement**.

---

# 9. FLOPS regularization

SPLADE uses a **FLOPS regularizer** to encourage efficient sparsity.

For vocabulary dimension \(j\), average activation is:

\[
\bar a_j
=
\frac{1}{N}
\sum_{i=1}^{N}w_j^{(d_i)}
\]

The regularization objective is:

\[
L_{\mathrm{FLOPS}}
=
\sum_{j\in V}\bar a_j^2
\]

The square strongly penalizes dimensions that are activated frequently across documents.

### Why?

Consider:

```text
heart
 → millions of documents

infarction
 → thousands of documents
```

A posting list for `heart` is much more expensive to traverse.

FLOPS therefore encourages the model to avoid making the same vocabulary dimensions active everywhere.

---

# 10. Training objective

SPLADE needs to balance two goals:

### Goal 1 — relevance

Learn to rank relevant documents higher.

\[
L_{\text{rank}}
\]

### Goal 2 — efficiency

Keep query/document representations sparse.

\[
L_{\text{FLOPS}}
\]

Conceptually:

\[
L =
L_{\text{ranking}}
+
\lambda_qL_{\text{FLOPS}}^q
+
\lambda_dL_{\text{FLOPS}}^d
\]

Separate regularization strengths can be used for queries and documents.

---

# 11. SPLADE scoring

Once query and document representations are produced:

\[
q,d \in \mathbb{R}^{|V|}
\]

the retrieval score is:

\[
\boxed{s(q,d)=q^Td}
\]

Expanded:

\[
s(q,d)=
\sum_{j\in V}q_jd_j
\]

But because the vectors are sparse, only overlapping active dimensions contribute.

So in practice:

\[
s(q,d)
=
\sum_{j\in
\operatorname{active}(q)
\cap
\operatorname{active}(d)}
q_jd_j
\]

---

# 12. SPLADE + inverted index

This is the most important systems concept.

Suppose SPLADE produces:

### D1

```text
heart       1.8
attack      1.5
cardiac     0.9
infarction  1.2
treatment   2.0
therapy     0.8
```

### D2

```text
cardiac     1.7
infarction  2.1
treatment   0.5
therapy     1.6
```

The inverted index stores:

```text
heart
 ├── D1 : 1.8

attack
 └── D1 : 1.5

cardiac
 ├── D1 : 0.9
 └── D2 : 1.7

infarction
 ├── D1 : 1.2
 └── D2 : 2.1

treatment
 ├── D1 : 2.0
 └── D2 : 0.5

therapy
 ├── D1 : 0.8
 └── D2 : 1.6
```

Notice:

> The inverted index contains **weighted postings**, not merely document IDs.

---

# 13. Query-time retrieval

Suppose the query is:

```text
"myocardial infarction treatment"
```

SPLADE might produce:

```text
infarction  → 2.5
myocardial   → 2.2
treatment    → 1.8
heart        → 1.1
therapy      → 0.7
```

We look up the posting lists for these active query terms.

Conceptually:

```text
infarction
 → D1, D2

myocardial
 → ...

treatment
 → D1, D2, D3

heart
 → D1, D3

therapy
 → D1, D2, D3
```

This gives the candidate documents.

---

# 14. Candidate generation + scoring

At a conceptual level:

```text
Query
  ↓
SPLADE sparse vector
  ↓
active query terms
  ↓
inverted-index posting lists
  ↓
candidate documents
  ↓
sparse dot-product scores
  ↓
Top-K
```

However, an optimized sparse retrieval engine does not necessarily materialize a candidate pool first and then perform separate full dot products.

It can accumulate scores directly while traversing posting lists:

```text
heart:
    D1 += q_heart × d1_heart
    D3 += q_heart × d3_heart

infarction:
    D1 += q_infarction × d1_infarction
    D2 += q_infarction × d2_infarction

treatment:
    D1 += q_treatment × d1_treatment
    D2 += q_treatment × d2_treatment
    D3 += q_treatment × d3_treatment
```

Then select Top-K.

Mathematically this is still:

\[
q^Td
\]

but the computation exploits sparsity and the inverted index.

---

# 15. Why the inverted index works

Think of the document-term matrix:

\[
D=
\begin{bmatrix}
1.8 & 1.5 & 1.2 & 2.0 & 0.8\\
0 & 0 & 2.1 & 0.5 & 1.6\\
1.4 & 0 & 0 & 1.7 & 0.7
\end{bmatrix}
\]

Instead of storing rows:

```text
D1 → [1.8, 1.5, 1.2, 2.0, 0.8]
D2 → [0,   0,   2.1, 0.5, 1.6]
D3 → [1.4, 0,   0,   1.7, 0.7]
```

the inverted index stores columns:

```text
heart
 → D1:1.8
 → D3:1.4

infarction
 → D1:1.2
 → D2:2.1

treatment
 → D1:2.0
 → D2:0.5
 → D3:1.7
```

This is essentially an efficient sparse representation of the document-term matrix.

---

# 16. SPLADE vs BM25

| Property | BM25 | SPLADE |
|---|---|---|
| Representation | Literal terms | Learned vocabulary terms |
| Neural model | No | Yes |
| Contextual | No | Yes |
| Expansion | No | Yes |
| Sparse | Yes | Yes |
| Inverted index | Yes | Yes |
| Learned term weights | Limited | Yes |
| Semantic matching | Limited | Stronger |
| Vocabulary mismatch | Problem | Reduced |

Mental model:

```text
BM25:

text
 ↓
literal words
 ↓
inverted index
 ↓
lexical scoring
```

```text
SPLADE:

text
 ↓
BERT
 ↓
learned vocabulary expansion
 ↓
sparse weighted terms
 ↓
inverted index
 ↓
sparse dot product
```

---

# 17. SPLADE vs dense retrieval + HNSW

### Dense retrieval

```text
Query
 ↓
dense vector
 ↓
HNSW / ANN
 ↓
nearest vectors
```

Core idea:

\[
\text{navigate a geometric vector space}
\]

### SPLADE

```text
Query
 ↓
sparse vocabulary vector
 ↓
inverted index
 ↓
weighted posting lists
 ↓
Top-K
```

Core idea:

\[
\text{retrieve through vocabulary dimensions}
\]

Key distinction:

\[
\boxed{\text{HNSW = approximate geometric search}}
\]

\[
\boxed{\text{SPLADE = sparse inverted-index retrieval}}
\]

---

# 18. Why SPLADE is still semantic

The vocabulary dimensions are lexical, but their activations are generated by a contextual neural model.

For example:

```text
Query:
"myocardial infarction"

SPLADE:
myocardial
infarction
heart
cardiac
attack
...
```

A document containing:

```text
"heart attack"
```

may therefore share important SPLADE dimensions with the query.

So semantic understanding is converted into **vocabulary-level activation**.

---

# 19. The complete architecture

```text
                    INPUT TEXT
                        │
                        ▼
                 WordPiece tokenizer
                        │
                        ▼
                 BERT / DistilBERT
                        │
                        ▼
              contextual representations
                    h1 ... hN
                        │
                        ▼
              MLM vocabulary projection
                        │
                        ▼
               vocabulary scores
                        │
                        ▼
                  ReLU + log
                        │
                        ▼
                  MAX / SUM pool
                        │
                        ▼
          sparse 30,522-dimensional vector
                        │
                        ▼
              FLOPS regularization
                        │
                        ▼
                 SPARSE VECTOR
                        │
                        ▼
                INVERTED INDEX
                        │
                        ▼
              sparse dot-product scoring
                        │
                        ▼
                     TOP-K
```

---

# 20. Offline vs online

## Offline — document indexing

```text
Documents
   ↓
SPLADE encoder
   ↓
sparse document vectors
   ↓
inverted index
```

Document representations can be precomputed.

## Online — query retrieval

```text
User query
   ↓
SPLADE encoder
   ↓
sparse query vector
   ↓
posting-list lookup
   ↓
score accumulation
   ↓
Top-K documents
```

This separation is important for production retrieval systems.

---

# 21. SPLADE-doc

The paper also introduces **SPLADE-doc**.

The key idea is to make document-side representations especially suitable for offline indexing.

The score can be written as:

\[
s(q,d)=\sum_{j\in q}w_j^d
\]

The document representation can be computed and indexed offline.

This reduces online computation.

---

# 22. Distillation

The paper also uses knowledge distillation.

A stronger cross-encoder can act as a teacher:

```text
Query + Document
       ↓
Cross-encoder teacher
       ↓
relevance score
       ↓
train SPLADE student
```

Hard negatives are particularly useful because they are documents that look relevant but should rank lower.

The resulting distilled SPLADE model improves retrieval effectiveness.

---

# 23. Most important formulas

### Vocabulary projection

\[
w_{ij}
=
\text{transform}(h_i)^TE_j+b_j
\]

### Activation transformation

\[
\log(1+\operatorname{ReLU}(w_{ij}))
\]

### Original SUM pooling

\[
w_j
=
\sum_i
\log(1+\operatorname{ReLU}(w_{ij}))
\]

### SPLADE-max

\[
w_j
=
\max_i
\log(1+\operatorname{ReLU}(w_{ij}))
\]

### Retrieval score

\[
\boxed{s(q,d)=q^Td}
\]

### FLOPS regularization

\[
\boxed{
L_{\mathrm{FLOPS}}
=
\sum_{j\in V}\bar a_j^2
}
\]

---

# 24. Interview/exam mental model

If asked:

**"Explain SPLADE in 30 seconds."**

Answer:

> SPLADE uses a BERT-style model to map each input token into importance scores over the entire vocabulary. These scores are transformed with ReLU and log saturation and pooled to produce a high-dimensional but sparse vocabulary-level vector. Because the vector is sparse and its dimensions correspond to vocabulary terms, document vectors can be stored in a weighted inverted index. At query time, the query is encoded similarly, its active terms retrieve posting lists, and sparse dot-product contributions are accumulated to rank documents. FLOPS regularization encourages sparsity and controls retrieval cost.

---

# 25. The one diagram to memorize

```text
                    SPLADE

                     TEXT
                      │
                      ▼
                    BERT
                      │
                      ▼
             vocabulary scores
                      │
                      ▼
                ReLU + log
                      │
                      ▼
                MAX pooling
                      │
                      ▼
          SPARSE VOCAB VECTOR
                      │
                      ▼
              INVERTED INDEX
                      │
              ┌───────┴────────┐
              │                │
         query term        posting list
              │                │
              └───────┬────────┘
                      ▼
               q_j × d_j
                      │
                      ▼
               score accumulator
                      │
                      ▼
                    TOP-K
```

## Final intuition

> **SPLADE is essentially a neural model that learns a sparse, weighted bag-of-vocabulary representation. That representation can be plugged into an inverted index, giving semantic expansion without abandoning classical sparse retrieval infrastructure.**

### Remember these 4 words:

**BERT → EXPANSION → SPARSITY → INVERTED INDEX**
