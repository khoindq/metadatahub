# MetadataHub Drill-Down Benchmark

This benchmark tests **Tier 2 tree navigation** — the unique capability that differentiates MetadataHub from basic RAG systems.

## What's Being Tested

### Tier 1: Source Retrieval
- Standard vector similarity search
- Find which file contains the answer
- Metrics: Recall@K, MRR

### Tier 2: Tree Drill-Down (The MetadataHub Advantage)
- Navigate the hierarchical tree index to find specific content
- For Excel: Sheet → Row → Column
- For Code: Class → Method
- For Markdown: Section → Subsection → Paragraph
- Metrics: Path accuracy, content match, depth reached

## Corpus

Three carefully designed files testing different tree structures:

### 1. `financial_q3_report.xlsx`
Multi-sheet Excel file with:
- **Revenue sheet**: Q1-Q4 data by product/cloud/services
- **Expenses sheet**: Category breakdown with budget and variance
- **Summary sheet**: Key metrics, YoY comparison, regional data

### 2. `auth_module.py`
Real Python authentication module with:
- `AuthService` class: authenticate(), logout(), change_password()
- `TokenManager` class: create_token(), validate_token(), refresh_token()
- `PasswordHasher` class: hash_password(), verify_password()
- Proper docstrings, error handling, and implementation

### 3. `api_documentation.md`
Nested markdown documentation with:
- Authentication (Login, Token Refresh, Logout)
- Data Operations (Create, Query, Update, Delete)
- Batch Operations
- Webhooks
- Rate Limits
- Error Handling

## Ground Truth

30 queries (10 per file type) testing drill-down navigation:

| Category | Queries | Example |
|----------|---------|---------|
| Excel Cell | 10 | "What is Q3 Cloud revenue?" → Sheet:Revenue → Row:Q3 → Col:Cloud |
| Code Method | 10 | "How does TokenManager validate tokens?" → Class:TokenManager → Method:validate_token |
| Markdown Section | 10 | "What are login request parameters?" → Authentication → Login → Request Parameters |

## Running the Benchmark

```bash
# From metadatahub-eval root:
source benchmark/.venv/bin/activate
python benchmark/drilldown/run_drilldown_benchmark.py --verbose

# Skip reindexing (use existing):
python benchmark/drilldown/run_drilldown_benchmark.py --skip-ingest --verbose
```

## Metrics

### Tier 1 Metrics
- **Recall@1**: Did the expected file rank first?
- **Recall@3/5**: Was expected file in top 3/5?
- **MRR**: Mean Reciprocal Rank

### Tier 2 Metrics
- **Path Accuracy**: % of path elements correctly navigated
- **Full Path Match**: Did we reach the exact expected location?
- **Content Match**: Does the content contain expected values?
- **Depth Reached**: How deep into the tree did we navigate?

### Combined
- **Overall Success**: Tier 1 hit AND (path partially matched OR content matched)

## Expected Results

A well-functioning MetadataHub should achieve:
- **Tier 1 Recall@1**: >90% (source files are distinctive)
- **Tier 2 Path Accuracy**: >60% (tree navigation works)
- **Content Match**: >80% (correct information retrieved)

## Directory Structure

```
benchmark/drilldown/
├── README.md                       # This file
├── corpus/
│   ├── financial_q3_report.xlsx    # Excel test file
│   ├── auth_module.py              # Python code test file
│   └── api_documentation.md        # Markdown test file
├── ground_truth_drilldown.json     # 30 queries with expected paths
├── run_drilldown_benchmark.py      # Benchmark runner
├── create_excel.py                 # Script to generate Excel file
├── store/                          # MetadataHub index (generated)
└── results/                        # Benchmark results (generated)
```

## Why This Matters

Basic RAG can find "auth_module.py contains authentication code."

MetadataHub can find "The `validate_token` method in `TokenManager` class checks token expiration by comparing `time.time()` with `payload.expires_at` and raises `TokenExpiredError` if expired."

That precision is the difference between a helpful answer and a hallucinated one.
