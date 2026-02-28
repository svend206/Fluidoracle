# Chunking and Retrieval Audit

**Date:** 2026-02-26
**Author:** openclaw
**Status:** Draft — awaiting Erik's review

---

## 1. What the Current Implementation Does

### Chunking Strategy: Parent-Child

The system uses a two-level chunking architecture:

- **Parent chunks:** ~2000 characters with 200-char overlap. These are the context windows delivered to the LLM when answering questions.
- **Child chunks:** ~400 characters with 50-char overlap. These are what the search indexes match against. Each child maps to exactly one parent via `parent_id` metadata.

Splitting is character-based with heuristic boundary detection — the `chunk_text()` function tries paragraph breaks first (last 20% of chunk), then sentence boundaries, then word boundaries. No semantic or structural awareness.

### Search Pipeline: Three Stages

**Stage 1 — Hybrid Search (Semantic + BM25)**

- Semantic: Embeds the query via OpenAI `text-embedding-3-small` (1536 dims), queries the ChromaDB child collection with cosine distance, returns top 30 hits.
- BM25: Loads a pre-built `rank_bm25.BM25Okapi` index from a pickle file. Tokenizes query with a simple regex tokenizer. Returns top 30 non-zero-score hits.
- Merge: Normalizes each method's scores to [0, 1] independently, then combines with weighted sum (60% semantic, 40% BM25). Deduplicates by `child_id` — if a chunk appears in both result sets, scores are combined. Takes top 20 merged candidates.

**Stage 2 — Parent-Child Resolution**

- For each candidate child, looks up the parent chunk in the parent collection.
- Deduplicates: if multiple children map to the same parent, keeps the child with the highest combined score.
- Falls back to using child text as context if no parent collection exists.

**Stage 3 — Cross-Encoder Reranking**

- Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` (local, ~80MB).
- Scores each (query, parent_text) pair.
- Applies sigmoid to raw scores, sorts, returns top 10.

### Verification Layer (verified_query.py)

Wraps the search pipeline with:
- **Confidence scoring** — HIGH (top score ≥ 0.75, ≥2 high-confidence matches from ≥2 sources), MEDIUM (top score ≥ 0.40), LOW (below 0.40).
- **Contradiction detection** — crude word-overlap check between top two results from different sources. Flags when overlap < 15%.
- **Vendor diversity analysis** — detects when all results come from a single manufacturer.
- **Gap tracker** — logs LOW-confidence queries to `gap-tracker.jsonl` for acquisition prioritization.
- **Correction pipeline** — interactive CLI for recording wrong answers.
- **Source humanization** — filename-to-display-name mapping (still has SprayOracle vendor patterns like Spraying Systems Co., Lechler, BETE — needs updating for hydraulic filter manufacturers).

### Table Enhancement (enhance_tables.py)

Addresses a real problem: numeric table chunks embed poorly. For parent chunks where the alphabetic character ratio is below 25%, the system generates a natural-language "index child" — a description of what the table contains, built from the source filename, preceding text-rich parents, and any headers found in the table text. This index child embeds well and routes searches to the table's parent via parent-child resolution.

### Batch Ingestion (batch_ingest.py)

- Recursively scans a directory for supported files (.pdf, .docx, .md, .txt, .rst).
- Content-hash manifest prevents duplicate ingestion.
- Auto-tags from directory structure and filename.
- Rebuilds BM25 once at the end, not per file.
- Progress tracking with ETA.

---

## 2. Gap Analysis Against Current Best Practices

### 2.1 Chunking

| What's There | What's Missing | Impact |
|---|---|---|
| Character-based splitting with boundary heuristics | **No markdown/structure-aware parsing.** The curated references are well-structured markdown with headers, lists, and tables. The chunker ignores all of this. A `## Section Header` has no special status — it can be split mid-section or orphaned from its content. | **HIGH.** Structural splitting would produce dramatically better chunk boundaries for the curated reference documents, which are the primary knowledge base. |
| Fixed 2000/400 char sizes | **No adaptive sizing.** A short, dense table and a long narrative section get the same treatment. | MEDIUM. The table enhancement script partially compensates, but only for numeric tables. |
| Parent-child hierarchy is two levels | **No document-level context injection.** "Late chunking" and "contextual retrieval" approaches prepend document title and section path to each chunk before embedding, so the embedding carries hierarchical context. Currently, child chunks are embedded in isolation — a chunk saying "this is typically 10 µm(c)" has no embedding context for what "this" refers to. | **HIGH.** Anthropic's contextual retrieval paper showed 49% reduction in retrieval failures by prepending a document summary + section context to each chunk before embedding. |
| — | **No semantic chunking.** Methods like Greg Kamradt's semantic chunking or Jina AI's late chunking split at natural topic boundaries by monitoring embedding similarity between consecutive sentences. | LOW-MEDIUM. The curated references are already well-structured, so structural splitting (by markdown headers) would capture most of the benefit. Semantic chunking matters more for unstructured documents like scraped web pages. |

### 2.2 Embeddings

| What's There | What's Missing | Impact |
|---|---|---|
| `text-embedding-3-small` (OpenAI, 1536 dims) | **This is fine for now.** It's fast, cheap ($0.02/1M tokens), and adequate for the collection size. | LOW. Upgrading to `text-embedding-3-large` or a specialized model isn't worth the cost until retrieval quality is measured and found wanting. |
| — | **No query expansion or HyDE.** The query embedding is a single shot — no hypothetical document generation, no query decomposition. | MEDIUM. For complex engineering questions ("What filter should I use for a cold-start system running ISO 46 oil at -20°F?"), generating a hypothetical answer first and embedding that would retrieve more relevant chunks. But this adds latency and an LLM call per query. |

### 2.3 Search & Ranking

| What's There | What's Missing | Impact |
|---|---|---|
| BM25 + semantic hybrid with linear combination | **No learned sparse retrieval (SPLADE/ColBERT).** | LOW for current scale. BM25 + dense hybrid is the standard approach and performs well. ColBERT (late interaction) is superior for precision but adds infrastructure complexity. Not worth it at <10K chunks. |
| Fixed 60/40 weighting | **No query-adaptive weighting.** Some queries benefit more from keyword matching (model numbers, ISO codes), others from semantic. | MEDIUM. A simple heuristic: if query contains an ISO standard number, model number, or part number, boost BM25 weight to 70-80%. |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker | **This is a general-purpose reranker trained on MS MARCO (web search).** It has no domain knowledge about engineering content. | MEDIUM. Fine for v1 — the cross-encoder still reads query+text together, which is the right architecture. A domain-fine-tuned reranker would help later, but the corpus isn't large enough to train one yet. |
| — | **No metadata filtering.** The search pipeline treats all chunks equally — no ability to filter by source type, authority score, curriculum phase, or fluid. The `artifact_vertical_tags`, `artifact_parameter_tags`, and `artifact_fluid_tags` tables in oracle.db are designed for exactly this, but there's no bridge between them and ChromaDB retrieval. | **HIGH.** When an engineer asks about water-glycol fluid compatibility, the system should be able to pre-filter or boost chunks tagged for that fluid. This is the entire purpose of the tagging pipeline in the schema — it has no consumer yet. |
| — | **No reciprocal rank fusion (RRF).** The current linear combination of normalized scores is sensitive to score distribution. RRF is more robust: `1 / (k + rank)` for each method, then sum. | LOW-MEDIUM. Would be a simple improvement to _merge_results(). The parameter `k` is typically 60. |

### 2.4 Context Assembly

| What's There | What's Missing | Impact |
|---|---|---|
| Parent chunks returned as-is | **No context compression.** Each parent is ~2000 chars. Returning 10 parents = ~20K chars of context, much of which may be tangential. | MEDIUM. LLM context windows are large enough that this isn't critical, but irrelevant context can distract the model. A future improvement: use the reranker score to truncate low-scoring results or apply extractive compression. |
| — | **No multi-hop retrieval.** If a question requires information from two different topics (e.g., "What filter micron rating do I need for ISO cleanliness code 16/14/11?"), the system retrieves based on the query as a whole. It can't decompose, retrieve separately, and combine. | LOW for v1. The curated references are structured to be self-contained per topic. Multi-hop becomes important when the knowledge base is larger and more fragmented. |

### 2.5 Domain-Specific Issues

| Issue | Detail | Impact |
|---|---|---|
| **Vendor patterns are spray-nozzle specific** | `verified_query.py` has `_VENDOR_PATTERNS` for Spraying Systems, Lechler, BETE, PNR-Italia, etc. None of these are hydraulic filter manufacturers. Parker, Donaldson, HYDAC, Pall, Schroeder, Bosch Rexroth are the relevant vendors. | **HIGH** — vendor diversity detection won't work at all until patterns are updated. |
| **Source humanization is spray-specific** | `_DISPLAY_NAME_OVERRIDES` and `humanize_source()` in both files reference spray catalog naming conventions. | MEDIUM — cosmetic but affects user trust in citations. |
| **BM25 tokenizer is naive** | The regex tokenizer splits on whitespace + punctuation. Technical terms like "ISO 4406" become two tokens, "β_x(c)" is mangled, "µm(c)" loses meaning. | MEDIUM — BM25 will underperform on the exact-match queries where it should excel (standard numbers, filter part numbers). |

---

## 3. Improvements Ranked by Impact

### Tier 1 — Do Before Sprint 2 Ingest

These directly affect the quality of the first knowledge base and are low-effort.

1. **Structure-aware chunking for markdown documents.** Split curated references at `## ` and `### ` header boundaries instead of by character count. Each section becomes a parent chunk (regardless of length, capped at ~4000 chars). Child chunks split normally within each section. This preserves the document's topic structure.
   - **Effort:** ~2 hours. Modify `chunk_text()` or add a `chunk_markdown()` path in `ingest.py`.
   - **Impact:** Every curated reference was written with clear section boundaries. Respecting them will produce dramatically more coherent chunks.

2. **Contextual chunk prefixing.** Before embedding each child chunk, prepend `"Document: {filename} | Section: {section_header} | "`. This gives the embedding model context about what the chunk belongs to.
   - **Effort:** ~1 hour. Modify `create_parent_child_chunks()`.
   - **Impact:** Directly addresses the "this" ambiguity problem. Costs nothing at query time — only affects the stored embedding.

3. **Update vendor patterns for hydraulic filter domain.** Replace spray nozzle vendor patterns with Parker, Donaldson, HYDAC, Pall, Schroeder, Bosch Rexroth, Eaton, MP Filtri.
   - **Effort:** 30 minutes.
   - **Impact:** Vendor diversity detection actually works.

### Tier 2 — Do During Sprint 2

4. **Metadata filtering bridge.** When the verified query system knows the fluid type or curriculum phase from the consultation context, pass metadata filters to ChromaDB's `where` clause. This requires:
   - Adding `curriculum_phase` and `fluid_tags` to chunk metadata during ingestion.
   - Accepting optional filter parameters in `search()`.
   - **Effort:** ~4 hours.
   - **Impact:** Precision improvement, especially as the knowledge base grows beyond the initial 12 documents.

5. **Query-adaptive BM25 weighting.** Simple regex detection: if query contains a pattern matching ISO/NAS/SAE standard numbers, part numbers, or model numbers, set BM25 weight to 0.75. Otherwise use default 0.60/0.40.
   - **Effort:** 1 hour.
   - **Impact:** Better retrieval for specification-lookup queries, which are a core use case.

6. **Replace linear score combination with RRF.** `combined_score = 1/(60 + semantic_rank) + 1/(60 + bm25_rank)`.
   - **Effort:** 30 minutes.
   - **Impact:** More robust score fusion, especially when score distributions differ significantly between methods.

### Tier 3 — Sprint 3+

7. **BM25 tokenizer improvement.** Recognize and preserve technical tokens: ISO codes, part numbers with slashes/dashes, Greek letters, units with parentheses. Add a synonym expansion layer (e.g., "beta ratio" → "β ratio", "micron" → "µm").
   - **Effort:** 2-3 hours.

8. **HyDE (Hypothetical Document Embeddings).** For complex queries, use the LLM to generate a hypothetical answer, embed that instead of the raw query. Improves recall for questions where the answer's vocabulary differs significantly from the question's.
   - **Effort:** 3-4 hours. Adds ~1 second latency per query.

9. **Domain-tuned reranker.** Once there are 50+ validated test cases (Sprint 3+), fine-tune the cross-encoder on engineering Q&A pairs.
   - **Effort:** Days. Requires training data collection.

10. **ColBERT or late-interaction retrieval.** Replace dense single-vector search with token-level interaction. Better precision for queries with specific technical terms.
    - **Effort:** Significant infrastructure change. Not warranted at current scale.

---

## 4. Concrete Recommendations

### Keep
- **Parent-child architecture.** This is sound. Searching on small chunks and returning large context windows is the right approach for LLM consumption.
- **Hybrid BM25 + semantic search.** Correct for engineering content where exact terms matter as much as conceptual similarity.
- **Cross-encoder reranking.** The right architecture even if the model is generic.
- **Table enhancement script.** Clever solution to a real problem. The index-child pattern is worth keeping.
- **Gap tracker and correction pipeline.** Essential feedback loops for knowledge base improvement.
- **Batch ingestion with manifest.** Deduplication and progress tracking are exactly what's needed for bulk loading.

### Modify Before First Ingest
- **Add markdown-aware chunking path** — split at `##`/`###` boundaries for `.md` files.
- **Add contextual prefix to child chunk embeddings** — `Document: {source} | Section: {header}`.
- **Update vendor patterns** — hydraulic filter manufacturers, not spray nozzle manufacturers.

### Add During Sprint 2
- **Metadata filtering** — fluid type, curriculum phase, source authority.
- **Query-adaptive BM25 weighting** — boost keyword search for specification queries.
- **RRF score fusion** — replace linear combination.

### Platform-Level: Move Domain Config Out of Python

This is a scaling problem, not just a FilterOracle problem. Every file listed below has domain-specific content hardcoded in Python that will break or be irrelevant for the next vertical:

| File | Hardcoded Domain Content |
|---|---|
| `verified_query.py` | `_VENDOR_PATTERNS` (spray nozzle manufacturers), `_DISPLAY_NAME_OVERRIDES` (spray catalog names) |
| `enhance_tables.py` | `humanize_source()` catalog map (spray catalog prefixes: `cat75hyd`, `c12b`, `tm402`, etc.) |

**The fix:** Vendor/manufacturer identity belongs in `oracle.db`, not in retrieval code.

1. **Use the existing `manufacturers` table** — already has `id`, `name`, `website`. Add a `filename_patterns` column (JSON array of regex patterns that identify this manufacturer's documents in filenames).
2. **`_detect_vendor()` becomes a database lookup** — loads manufacturer patterns from oracle.db once, caches in memory. No hardcoded Python dicts.
3. **`humanize_source()` reads display names from manufacturers + a `document_display_names` table** (or a column on `knowledge_artifacts`) instead of Python maps.
4. **Vertical bootstrap registers its manufacturers** — just like it already registers parameters and outcome templates. New vertical = new manufacturers and patterns. Zero changes to retrieval engine code.

**The principle:** The platform owns the engine. Verticals own the configuration data. Anywhere domain-specific content is hardcoded in Python, it should move to oracle.db or the vertical's config YAML.

### Defer
- HyDE, ColBERT, domain-tuned reranker, semantic chunking — all good ideas but the knowledge base needs to exist before optimizing retrieval quality further. Measure first, then optimize.

---

## Appendix: File-by-File Notes

| File | Purpose | Issues |
|---|---|---|
| `config.py` | Central configuration | `PROJECT_ROOT` path was recently fixed (Entry 002). All constants are reasonable defaults. |
| `ingest.py` | Single-doc ingestion + BM25 rebuild | Chunking needs markdown awareness. Embedding is fine. Storage is fine. |
| `batch_ingest.py` | Directory-level bulk ingestion | Well-designed. Auto-tagging from directory structure is smart. |
| `hybrid_search.py` | Three-stage retrieval pipeline | Core pipeline is solid. Needs metadata filtering and RRF. Weight override via config mutation is fragile (non-thread-safe). |
| `verified_query.py` | Verification wrapper | Vendor patterns need domain update. Contradiction detection is crude but directionally useful. |
| `enhance_tables.py` | Table discoverability | Good approach. `humanize_source()` needs hydraulic filter catalog patterns. |
