# HNSW Search — Revision Notes

## 1. What is HNSW?

**HNSW = Hierarchical Navigable Small World.**

It is an approximate nearest-neighbor (ANN) data structure built from multiple layers of proximity graphs.

Core idea:

> **Use upper layers for cheap global navigation, then use Layer 0 for detailed local search.**

The original HNSW paper describes the structure as hierarchical proximity graphs over nested subsets of elements, with node levels chosen using an exponentially decaying distribution.  
Source: *Malkov & Yashunin, Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs.*

---

## 2. Why not brute force?

For a query `q` and `N` vectors:

```text
compare q against every vector
→ O(N) distance evaluations
```

HNSW instead builds a graph and **navigates through it**, so it does not need to inspect every vector.

---

## 3. The key HNSW intuition

Think of HNSW like a **skip list, but with proximity graphs instead of linked lists**.

```text
Layer 3     sparse, long-range connections
   ↓
Layer 2     fewer nodes, longer-range connections
   ↓
Layer 1     more nodes, shorter connections
   ↓
Layer 0     all nodes, detailed local search
```

Upper layers answer:

> **Where is the query region?**

Layer 0 answers:

> **Which points are actually nearest?**

---

# 4. HNSW Search = two phases

## Phase A — Upper-layer navigation

Start from the HNSW entry point.

At each upper layer:

```text
current = best node found so far
look at its neighbors
move toward the query
```

The paper uses `ef = 1` in the upper layers, which effectively gives **greedy search**.

```text
Layer 3 → greedy
Layer 2 → greedy
Layer 1 → greedy
```

When a local minimum is reached, descend to the next layer.

The same point found as the best point in the higher layer becomes the starting point for the lower layer.

---

## Phase B — Layer 0 search

At Layer 0, HNSW performs a broader **best-first graph search** controlled by `ef`.

This is where most of the recall-oriented exploration happens.

---

# 5. Is HNSW search BFS?

### Not exactly.

It is better described as:

> **Best-first graph search / beam-style graph search**

BFS uses a FIFO queue:

```text
first discovered → first explored
```

HNSW uses a **min-heap ordered by distance to the query**:

```text
closest discovered unexplored node → explored first
```

So:

```text
BFS:
A → B → C → D

HNSW:
A
├── B (distance 10)
├── C (distance 4)   ← explore first
└── D (distance 7)
```

---

# 6. The three important structures

The HNSW `SEARCH-LAYER` maintains three conceptual sets/queues.

## `V` — Visited

Nodes already seen.

Purpose:

```text
avoid evaluating the same node repeatedly
```

---

## `C` — Candidate set

Nodes that have been discovered but **not yet explored**.

Think:

> **C = FUTURE WORK**

It is ordered by distance to the query.

Therefore we take:

```text
closest node in C
```

next.

Typically implemented conceptually as a **min-heap**.

---

## `W` — Working/result set

The best nodes discovered so far.

Think:

> **W = BEST SO FAR**

Its size is bounded by `ef`.

```text
|W| <= ef
```

To efficiently know the worst current retained candidate, think of `W` as a **max-heap** by distance.

---

# 7. The most important mental model

Remember:

```text
C = nodes I may still explore
W = best nodes I have discovered so far
V = nodes I have already visited
```

Or even shorter:

```text
C → FUTURE
W → BEST SO FAR
V → SEEN
```

---

# 8. The SEARCH-LAYER algorithm

Conceptual pseudocode:

```python
def search_layer(q, entry, ef):

    visited = {entry}

    candidates = min_heap([entry])
    results = max_heap([entry])

    while candidates:

        current = pop_closest(candidates, q)

        worst = furthest(results, q)

        # stopping condition
        if distance(current, q) > distance(worst, q):
            break

        for neighbor in neighbors(current):

            if neighbor in visited:
                continue

            visited.add(neighbor)

            if (
                len(results) < ef
                or distance(neighbor, q) < distance(worst, q)
            ):
                push(candidates, neighbor)
                push(results, neighbor)

                if len(results) > ef:
                    remove_furthest(results)

    return results
```

This follows the structure of Algorithm 2 in the original paper.

---

# 9. The "weird" stopping condition

This is one of the most important things to remember.

Let:

- `c` = **closest unexplored node in candidate heap `C`**
- `f` = **furthest node currently retained in `W`**

Stop when:

```text
distance(q, c) > distance(q, f)
```

or:

\[
d(q,c) > d(q,f)
\]

### Why?

Suppose:

```text
ef = 3

W:
A = 2
B = 3
C = 5   ← worst current result

C:
X = 7   ← closest unexplored candidate
Y = 9
Z = 12
```

Since:

```text
closest unexplored = 7
worst current result = 5
```

and:

\[
7 > 5
\]

we stop.

### Intuition

Even the **best unexplored candidate** is already farther away than the worst node in our current `ef`-sized result set.

So there is no reason to keep expanding the frontier.

---

# 10. Why `ef > 1` matters

A purely greedy search can get trapped.

Example:

```text
current
   |
   A
   |
   B -------- X -------- Z
```

Suppose:

```text
distance(current, q) = 8
distance(A, q)       = 7
distance(B, q)       = 6
distance(X, q)       = 9
distance(Z, q)       = 1
```

A purely greedy algorithm reaches `B` and refuses to move to `X` because:

```text
9 > 6
```

But going through `X` leads to the excellent result `Z`.

With a wider candidate/result set (`ef > 1`), HNSW can preserve alternative paths instead of committing to a single greedy route.

Therefore:

```text
ef ↑
→ more exploration
→ better chance of escaping local minima
→ usually higher recall
→ higher query cost
```

---

# 11. `ef` is NOT the same as `K`

If you ask for:

```text
K = 10
```

that means:

> Return 10 nearest neighbors.

But you might search with:

```text
ef = 100
```

meaning:

> Allow a broader working set during search.

So:

```text
K  = final number of results
ef = search effort / exploration width
```

Usually:

```text
ef >= K
```

---

# 12. `M` vs `ef`

These are frequently confused.

## `M`

Controls the **graph structure**.

Roughly:

> How many connections are maintained per node.

Larger `M`:

```text
denser graph
→ more memory
→ potentially better connectivity/recall
```

## `ef`

Controls the **search process**.

Larger `ef`:

```text
more candidates explored
→ more distance computations
→ higher latency
→ generally higher recall
```

Remember:

```text
M  = graph connectivity
ef = search effort
```

---

# 13. `efConstruction`

There is another parameter:

```text
efConstruction
```

This is used while **building the HNSW index**.

It controls how much search effort is used to find candidate neighbors for a newly inserted node.

Therefore:

```text
efConstruction
→ build-time search effort

ef
→ query-time search effort
```

Higher `efConstruction` generally means:

```text
more expensive index construction
→ potentially better graph quality
```

---

# 14. Why upper layers use `ef = 1`

Upper layers contain far fewer nodes.

Their main job is not final recall.

Their job is:

> **quickly move to the right region of the space.**

So HNSW can use:

```text
ef = 1
```

and perform essentially greedy routing.

Then Layer 0 performs the more expensive search.

Thus:

```text
cheap global routing
        +
expensive local refinement
```

---

# 15. Complete search picture

```text
                ENTRY POINT
                     |
                     v
            +----------------+
            |    Layer 3     |
            |    ef = 1      |
            +----------------+
                     |
                     v
            +----------------+
            |    Layer 2     |
            |    ef = 1      |
            +----------------+
                     |
                     v
            +----------------+
            |    Layer 1     |
            |    ef = 1      |
            +----------------+
                     |
                     v
            +----------------+
            |    Layer 0     |
            |    ef = large   |
            +----------------+
                     |
                     v
                  TOP-K
```

---

# 16. One complete example

Suppose:

```text
K = 3
ef = 5
```

Start from entry node `A`.

```text
A → B, C
```

Candidate heap:

```text
C = {B, C}
```

Suppose:

```text
B = distance 7
C = distance 8
```

Explore `B` first.

`B` discovers:

```text
D = 6
E = 5
```

Now the working set improves:

```text
W = {E(5), D(6), B(7), C(8)}
```

Explore the closest unexplored candidate.

Suppose `E` discovers:

```text
X = 3
```

Now:

```text
W = {X(3), E(5), D(6), B(7), C(8)}
```

Because:

```text
ef = 5
```

all five can currently remain.

Continue exploring promising candidates.

Eventually, suppose:

```text
W:
X = 3
Z = 4
Y = 5
D = 6
B = 7

closest candidate left = 9
```

Since:

\[
9 > 7
\]

stop.

Return the best `K = 3`:

```text
X, Z, Y
```

---

# 17. Why HNSW is fast

The hierarchy separates distance scales.

Upper layers:

```text
few nodes
long edges
global movement
```

Lower layers:

```text
many nodes
short edges
local refinement
```

The original paper argues that the exponentially decreasing node population produces an expected number of layers of `O(log N)`, and under its stated assumptions each layer requires bounded work, giving logarithmic routing behavior. The authors also note that the idealized analysis depends on assumptions that are harder to guarantee in high-dimensional spaces.

---

# 18. Neighbor selection — another key HNSW idea

HNSW does not necessarily connect a new node to only its closest `M` candidates.

Why?

Because the closest candidates may all lie in the same direction/cluster.

Example:

```text
          A
         /
        B
       /
      Q -------- C
       \
        D
```

You want diverse connections rather than redundant ones.

The paper's heuristic therefore considers the distances between candidate nodes and the already selected neighbors, helping preserve diverse routing paths and connectivity, especially for clustered data.

---

# 19. HNSW construction in one picture

When inserting a new node `q`:

```text
1. Randomly choose q's maximum layer
                 ↓
2. Start from current entry point
                 ↓
3. Greedily descend through upper layers
                 ↓
4. At q's participating layers:
      run SEARCH-LAYER with efConstruction
                 ↓
5. Select neighbors
                 ↓
6. Add bidirectional connections
                 ↓
7. Continue down to Layer 0
                 ↓
8. Possibly update entry point
```

The paper's Algorithm 1 follows this insertion structure.

---

# 20. Exam/interview summary

### What is HNSW?

A hierarchical proximity-graph ANN index.

### Why hierarchy?

Separate long-range/global navigation from short-range/local refinement.

### What happens at upper layers?

Greedy best-next-node routing (`ef = 1`).

### What happens at Layer 0?

Broader best-first exploration controlled by `ef`.

### What is `C`?

Candidate nodes waiting to be explored.

### What is `W`?

Best nodes discovered so far.

### What is `V`?

Visited nodes.

### What data structure conceptually backs `C`?

Min-heap by distance to query.

### What does `W` need?

Efficient access to its worst/furthest element; conceptually a max-heap.

### What is the stopping condition?

\[
d(q,c) > d(q,f)
\]

where `c` is the closest unexplored candidate and `f` is the furthest current retained result.

### Why is `ef` important?

It controls exploration breadth and therefore the recall/latency trade-off.

### `M` vs `ef`?

```text
M  → graph connectivity
ef → search effort
```

### `efConstruction`?

Build-time search effort used to construct better connections.

---

# 21. The one mental model to memorize

```text
HNSW QUERY

        "Get me roughly there"
                    ↓
             upper layers
              greedy search
                    ↓
        "Now search properly"
                    ↓
               Layer 0
          best-first / beam search
                    ↓
            maintain C + W
                    ↓
      stop when closest(C) > worst(W)
                    ↓
                 TOP-K
```

**One-line takeaway:**

> HNSW search is essentially **best-first graph search with a bounded candidate/result set at Layer 0, preceded by greedy navigation through progressively sparser upper layers**.

---

## Source

Based on the uploaded paper:

**Yu. A. Malkov, D. A. Yashunin — “Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs.”**

The paper's `SEARCH-LAYER` defines the visited set, candidate set, dynamic result set, and the stopping condition; Algorithm 5 then applies this layer-by-layer search from the entry point down to Layer 0.
