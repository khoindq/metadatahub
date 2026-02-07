# MetadataHub (Search) — System Plan

## Feeding AI Agents with a Hybrid, File-Based Knowledge Index

---

## 1. What Is MetadataHub

MetadataHub is a **file-based, open-source knowledge index** that sits between your raw documents and your AI agents. It combines two retrieval strategies — fast vector search for source detection and deep reasoning-based tree search for precise extraction — inspired by PageIndex but designed around a **skills-based agent architecture** instead of MCP.

```
┌─────────────────────────────────────────────────────┐
│                  RAW SOURCES                        │
│  PDFs, Excel, Markdown, Code, HTML, CSV, Docs ...  │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   INGEST LAYER  │
              │  (AI Sampling   │
              │   + Strategy)   │
              └────────┬────────┘
                       │
        ┌──────────────▼──────────────┐
        │       MetadataHub Store     │
        │  ┌───────────┬────────────┐ │
        │  │ Vector DB │ Tree Index │ │
        │  │ (FAISS/   │ (JSON     │ │
        │  │  file)    │  trees)   │ │
        │  └───────────┴────────────┘ │
        │  ┌────────────────────────┐ │
        │  │  Source Registry       │ │
        │  │  (catalog.json)        │ │
        │  └────────────────────────┘ │
        └──────────────┬──────────────┘
                       │
              ┌────────▼────────┐
              │  RETRIEVAL LAYER│
              │  Skill-based    │
              │  Agent Feed     │
              └─────────────────┘
```

---

## 2. Core Design Principles

| Principle | Decision |
|---|---|
| **File-based everything** | No servers, no Docker, no external DBs. The entire index is a folder of JSON + FAISS `.index` files |
| **AI-first ingestion** | Claude (via OAuth token) samples every document first, decides a strategy, then indexes |
| **Two-tier retrieval** | Tier 1: vector search → which source? Tier 2: tree reasoning → which section/answer? |
| **Skills, not MCP** | Agent consumes MetadataHub through skill files (SKILL.md + scripts), not protocol servers |
| **Open source** | MIT license, plain Python, minimal dependencies |

---

## 3. The Three Layers (Detailed)

### Layer 1 — Ingest & Sampling

This is where MetadataHub is fundamentally different from basic RAG. Instead of blindly chunking, **Claude samples the document first** and decides how to process it.

**Step 1: File Detection & Typing**

Every file dropped into the `/inbox` folder gets classified:

```
inbox/
  annual_report.pdf
  sales_q3.xlsx
  api_reference.md
  app.py
  meeting_notes.docx
```

A lightweight classifier (file extension + magic bytes + first 500 bytes sampling) produces a **file card**:

```json
{
  "id": "src_a1b2c3",
  "filename": "annual_report.pdf",
  "type": "pdf",
  "size_kb": 4200,
  "pages": 87,
  "sampled": false,
  "strategy": null
}
```

**Step 2: AI Sampling (Claude via OAuth)**

For each file, Claude receives a **sample** (not the whole file) and decides the indexing strategy. The sample includes:

- First 2 pages / 2000 chars (for text)
- Sheet names + header rows + first 5 data rows (for Excel)
- File tree + first 200 lines (for code)
- Table of contents if available

Claude is prompted to return a **strategy object**:

```json
{
  "doc_nature": "financial_report",
  "has_structure": true,
  "recommended_approach": "tree_index",
  "convert_to_plaintext": false,
  "key_sections": ["Revenue", "Risk Factors", "Balance Sheet"],
  "estimated_nodes": 24,
  "special_handling": "contains tables — extract as structured data",
  "summary": "FY2025 annual report with standard SEC filing structure..."
}
```

**Strategy decision matrix** (Claude decides, but here's the logic):

| Document Type | Structured? | Strategy |
|---|---|---|
| PDF with ToC / headings | Yes | **Tree index** (PageIndex-style) |
| Excel / CSV | Yes | **Schema index** (headers + sample rows as metadata) |
| Long markdown / docs | Yes | **Tree index** from headings |
| Code files | Yes | **Symbol index** (functions, classes, imports) |
| Flat text / notes | No | **Plain text → chunk + embed only** |
| Images / scanned PDF | N/A | **OCR → then re-classify** |

**Step 3: Conversion**

Based on strategy, files get converted to an indexable form:

- PDFs → extracted text (per page) + structural markers
- Excel → each sheet becomes a "document" with schema metadata
- Code → AST-parsed symbols + docstrings
- Everything else → plain text with paragraph boundaries

Output: one `.txt` or `.json` per source in `/converted/`

---

### Layer 2 — Indexing (The MetadataHub Store)

Two indexes are built simultaneously. Both are **files on disk**.

#### 2A. Vector Index (Tier 1 — "Which source?")

Purpose: given a query, quickly identify the **top 3–5 source documents** that are likely relevant.

**What gets embedded:**

Not the full document. Instead, embed the **document-level metadata card** — a curated summary produced by Claude during sampling:

```json
{
  "id": "src_a1b2c3",
  "title": "FY2025 Annual Report — Acme Corp",
  "summary": "Annual financial filing covering revenue ($2.1B), ...",
  "key_topics": ["revenue", "risk factors", "acquisitions", "guidance"],
  "doc_type": "financial_report",
  "date": "2025-03-15",
  "sections_overview": "12 major sections, 87 pages"
}
```

This means the vector index is **small** — one embedding per document, not thousands of chunks. For hundreds of documents, the FAISS index will be < 10MB.

**Implementation:**

- Embedding model: `all-MiniLM-L6-v2` (local, free, fast) or call Claude to produce a text summary that gets embedded
- Storage: FAISS flat index saved as `vector_store/index.faiss` + `vector_store/metadata.json`
- Search: cosine similarity, return top-5 source IDs

#### 2B. Tree Index (Tier 2 — "Which section?")

Purpose: once vector search identifies the source, the tree index enables **reasoning-based deep retrieval** within that source.

**One tree per document**, stored as JSON:

```
tree_index/
  src_a1b2c3.tree.json
  src_d4e5f6.tree.json
  ...
```

**Tree structure** (generated by Claude via OAuth):

```json
{
  "id": "src_a1b2c3",
  "root": {
    "node_id": "n0",
    "title": "FY2025 Annual Report",
    "summary": "Complete annual filing...",
    "page_range": [1, 87],
    "children": [
      {
        "node_id": "n1",
        "title": "Executive Summary",
        "summary": "CEO letter + key highlights...",
        "page_range": [1, 4],
        "children": [],
        "content_ref": "converted/src_a1b2c3_pages_1-4.txt"
      },
      {
        "node_id": "n2",
        "title": "Financial Statements",
        "summary": "Revenue, costs, balance sheet...",
        "page_range": [15, 45],
        "children": [
          {
            "node_id": "n2.1",
            "title": "Income Statement",
            "summary": "Revenue $2.1B, net income...",
            "page_range": [15, 22],
            "content_ref": "converted/src_a1b2c3_pages_15-22.txt"
          }
        ]
      }
    ]
  }
}
```

**For Excel / tabular data**, the tree is a **schema tree**:

```json
{
  "node_id": "n0",
  "title": "Q3 Sales Data",
  "summary": "3 sheets, 1,200 rows total sales transactions",
  "children": [
    {
      "node_id": "n1",
      "title": "Sheet: North America",
      "summary": "650 rows, columns: date, product, region, amount, rep",
      "sample_data": "Row 1: 2025-01-05, Widget Pro, California, $12,500, J.Smith",
      "stats": {"total_amount": "$4.2M", "date_range": "Jan-Mar 2025"}
    }
  ]
}
```

#### 2C. Source Registry (catalog.json)

The master catalog — a single JSON file that links everything together:

```json
{
  "version": "1.0",
  "last_updated": "2025-02-07T10:30:00Z",
  "sources": [
    {
      "id": "src_a1b2c3",
      "filename": "annual_report.pdf",
      "original_path": "inbox/annual_report.pdf",
      "type": "pdf",
      "strategy": "tree_index",
      "tree_path": "tree_index/src_a1b2c3.tree.json",
      "converted_path": "converted/src_a1b2c3/",
      "indexed_at": "2025-02-07T10:15:00Z",
      "summary": "FY2025 Annual Report — Acme Corp...",
      "tags": ["finance", "annual", "acme"]
    }
  ]
}
```

---

### Layer 3 — Retrieval (Skill-Based Agent Feed)

This is how the AI agent **consumes** MetadataHub. It's a **skill**, not an API.

#### The Skill File Structure

```
skills/
  metadatahub/
    SKILL.md              ← Instructions for the agent
    search.py             ← Vector search script
    deep_retrieve.py      ← Tree reasoning retrieval
    read_source.py        ← Fetch original content from a node
    config.json           ← Points to the MetadataHub store location
```

#### SKILL.md (what the agent reads)

```markdown
# MetadataHub Search Skill

## When to use
Use this skill when you need to find information across
the user's document library — reports, spreadsheets, 
code, notes, etc.

## Two-step retrieval

### Step 1: Find relevant sources
Run `search.py` with the user's query.
Returns top-5 matching documents with summaries.

### Step 2: Deep retrieve from a source  
Run `deep_retrieve.py` with the source ID + query.
You will receive the tree index. Reason over the tree 
nodes to decide which section(s) to read. Then call
`read_source.py` with the node ID to get the actual content.

## Important
- Always start with Step 1 (vector search)
- Only go to Step 2 when you need specific details
- For Excel sources, you can ask for raw data or summaries
- The tree has summaries at every level — often you 
  don't need to read the full content
```

#### Retrieval Flow

```
Agent receives user question
        │
        ▼
   ┌─────────────────────┐
   │ 1. search.py         │  ← Vector similarity on metadata cards
   │    "What was Acme's  │
   │     Q3 revenue?"     │
   │                      │
   │    Returns:          │
   │    → src_a1b2c3 (0.92)  Annual Report
   │    → src_d4e5f6 (0.78)  Q3 Sales Sheet
   └──────────┬──────────┘
              │
              ▼
   ┌─────────────────────┐
   │ 2. deep_retrieve.py  │  ← Agent reads the tree JSON
   │    source: src_a1b2c3│     and REASONS about which
   │                      │     node to visit
   │    Agent thinks:     │
   │    "Revenue is under │
   │     Financial →      │
   │     Income Statement"│
   │                      │
   │    Returns: node n2.1│
   └──────────┬──────────┘
              │
              ▼
   ┌─────────────────────┐
   │ 3. read_source.py    │  ← Fetches actual text from
   │    node: n2.1        │     the converted file
   │                      │
   │    Returns:          │
   │    "Revenue for Q3   │
   │     was $512M..."    │
   └──────────┬──────────┘
              │
              ▼
   Agent synthesizes answer with citation
```

---

## 4. Claude OAuth Integration

MetadataHub uses **Claude OAuth tokens** (not API keys) for all LLM operations during indexing. This keeps it free-tier friendly and aligned with how skills already authenticate.

**Where Claude is used:**

| Operation | Claude's Role | When |
|---|---|---|
| **Sampling** | Read sample, decide strategy | On ingest |
| **Summarization** | Produce metadata card + summary | On ingest |
| **Tree generation** | Build hierarchical tree from document structure | On ingest |
| **Curation** | Tag, categorize, link related sources | On ingest (batch) |
| **Tree search reasoning** | Decide which tree nodes to visit | On query (the agent itself does this) |

**OAuth flow:**

```
1. User authenticates once → gets OAuth token
2. Token stored in config.json (local, never committed)
3. Indexing scripts use token to call Claude for sampling/tree generation
4. Token refreshed automatically
```

At query time, no OAuth call is needed for Tier 1 (vector search is local). Tier 2 reasoning happens inside the agent that already has its own Claude session.

---

## 5. Folder Structure (The Whole System)

```
metadatahub/
│
├── inbox/                      ← Drop files here
│   ├── annual_report.pdf
│   ├── sales_q3.xlsx
│   └── ...
│
├── converted/                  ← Processed plain text / structured data
│   ├── src_a1b2c3/
│   │   ├── pages_1-4.txt
│   │   ├── pages_15-22.txt
│   │   └── ...
│   └── src_d4e5f6/
│       ├── sheet_north_america.json
│       └── ...
│
├── vector_store/               ← Tier 1 index
│   ├── index.faiss
│   └── metadata.json
│
├── tree_index/                 ← Tier 2 index (one tree per source)
│   ├── src_a1b2c3.tree.json
│   ├── src_d4e5f6.tree.json
│   └── ...
│
├── catalog.json                ← Master registry
│
├── skills/                     ← Agent-facing skill
│   └── metadatahub/
│       ├── SKILL.md
│       ├── search.py
│       ├── deep_retrieve.py
│       ├── read_source.py
│       └── config.json
│
├── scripts/                    ← CLI tools
│   ├── ingest.py               ← Main indexing pipeline
│   ├── sample.py               ← AI sampling step
│   ├── build_tree.py           ← Tree generation
│   ├── build_vectors.py        ← FAISS index builder
│   └── curate.py               ← Batch tagging/linking
│
├── config.json                 ← Global config + OAuth token ref
├── requirements.txt
└── README.md
```

**Total dependencies (target):**

```
faiss-cpu
sentence-transformers   (or skip if using Claude for embeddings)
pypdf
openpyxl
python-docx
tiktoken                (token counting)
httpx                   (Claude OAuth calls)
```

---

## 6. Build Phases

### Phase 1 — Foundation (Week 1–2)

- [ ] Folder structure + config schema
- [ ] File type detection + basic converters (PDF → text, XLSX → JSON, MD pass-through)
- [ ] Claude OAuth integration (authenticate, call, handle token refresh)
- [ ] AI sampling: send sample to Claude, get strategy back
- [ ] `catalog.json` creation and management

### Phase 2 — Indexing (Week 3–4)

- [ ] Tree index generation via Claude (for structured docs)
- [ ] Schema index generation for Excel/CSV
- [ ] Symbol index for code files
- [ ] FAISS vector index from metadata cards
- [ ] Batch ingestion CLI: `python ingest.py ./inbox/`

### Phase 3 — Retrieval Skill (Week 5)

- [ ] `search.py` — vector search, returns ranked sources
- [ ] `deep_retrieve.py` — loads tree, presents to agent for reasoning
- [ ] `read_source.py` — fetches content from converted files
- [ ] `SKILL.md` — complete agent instructions
- [ ] End-to-end test: drop file → ingest → query → answer

### Phase 4 — Polish & Open Source (Week 6)

- [x] Incremental re-indexing (only new/changed files)
- [x] Cross-source linking (Claude identifies related documents)
- [ ] Quality scoring (confidence metadata on each tree node)
- [x] README, examples, license
- [x] GitHub release prep

---

## 7. Key Differences from PageIndex

| Aspect | PageIndex | MetadataHub |
|---|---|---|
| **Retrieval** | Vectorless only (tree reasoning) | **Hybrid** — vector for source detection + tree for deep retrieval |
| **Agent integration** | MCP protocol | **Skill files** (SKILL.md + scripts) |
| **Document types** | Primarily PDFs | **Everything** — PDF, Excel, code, markdown, docs |
| **Ingestion intelligence** | Direct tree generation | **AI sampling first** → strategy per document |
| **Storage** | Proprietary cloud | **100% file-based** — a folder you can git-commit |
| **LLM dependency** | API calls for indexing + retrieval | OAuth for indexing; retrieval Tier 1 is **fully local** |
| **Excel/tabular handling** | Not specialized | **Schema trees** with stats and sample data |

---

## 8. Open Questions for You

1. **OAuth token source** — Are you using Claude.ai's OAuth (consumer), or an Anthropic org-level OAuth? This affects the auth flow and rate limits.

2. **Embedding model preference** — Local `sentence-transformers` (free, fast, private) or Claude-generated text summaries embedded via a small model? Local is simpler and keeps everything offline after indexing.

3. **Code indexing depth** — For code files: just top-level functions/classes, or do you want full AST parsing with dependency graphs?

4. **Update frequency** — Is this a "batch ingest once" system, or do documents change frequently and need watch/re-index?

5. **Multi-language** — Any documents in languages other than English?

---

*This plan is a living document. The architecture is intentionally simple — every piece of state is a file you can inspect, edit, or version control.*
