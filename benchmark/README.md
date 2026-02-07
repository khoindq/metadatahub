# RAG System Benchmark Suite

A comprehensive benchmark for comparing RAG (Retrieval-Augmented Generation) systems:
- **MetadataHub** - Hybrid vector + tree retrieval
- **LlamaIndex** - Popular RAG framework
- **LangChain + FAISS** - LangChain with FAISS vector store

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run benchmark on all systems
python run_benchmark.py

# Run specific systems
python run_benchmark.py --systems metadatahub llamaindex

# Save results
python run_benchmark.py --output results/benchmark_$(date +%Y%m%d).json
```

## Directory Structure

```
benchmark/
├── README.md                  # This file
├── requirements.txt           # Dependencies for all systems
│
├── corpus/                    # Test documents
│   ├── financial/            # Financial reports and budgets
│   │   ├── q3_revenue_report.md
│   │   ├── budget_summary.md
│   │   └── expense_report_jan.md
│   ├── code/                 # Source code samples
│   │   ├── auth_service.py
│   │   └── data_processor.py
│   └── docs/                 # Documentation
│       ├── installation_guide.md
│       ├── api_reference.md
│       └── architecture.md
│
├── ground_truth.json          # 50 queries with expected results
│
├── systems/                   # System runners
│   ├── base_runner.py        # Abstract base class
│   ├── metadatahub_runner.py # MetadataHub implementation
│   ├── llamaindex_runner.py  # LlamaIndex implementation
│   └── langchain_runner.py   # LangChain + FAISS
│
├── run_benchmark.py           # Main benchmark script
└── analyze_results.py         # Analysis and visualization
```

## Ground Truth

The benchmark includes **50 queries** across three categories:

| Category | Count | Description |
|----------|-------|-------------|
| Financial | 15 | Revenue, budget, expense queries |
| Code | 20 | Function lookup, class discovery, how-to |
| Documentation | 15 | Installation, API, architecture questions |

Each query includes:
- English and Vietnamese versions
- Expected source documents
- Expected answer keywords
- Difficulty level (easy/medium/hard)

## Metrics

### Recall@K
Measures whether relevant documents appear in top K results.

| Metric | Description |
|--------|-------------|
| Recall@1 | First result is relevant |
| Recall@3 | At least one relevant in top 3 |
| Recall@5 | At least one relevant in top 5 |
| Recall@10 | At least one relevant in top 10 |

### Mean Reciprocal Rank (MRR)
Average of 1/rank of first relevant result. Higher = better.

### Latency
- **Avg Latency**: Mean query time in milliseconds
- **P50 Latency**: Median query time
- **P95 Latency**: 95th percentile (worst case)

### Index Metrics
- **Index Size**: Storage space in MB
- **Index Time**: Time to build index
- **Chunks**: Number of indexed chunks

## Usage Examples

### Basic Benchmark

```bash
# Run all systems with default settings
python run_benchmark.py

# Output:
# 📄 Loading ground truth from ground_truth.json
#    Found 50 queries
# 
# 🚀 Starting benchmark with 3 systems
# ...
# 
# ============================================================
# COMPARISON SUMMARY
# ============================================================
# | Metric | MetadataHub | LlamaIndex | LangChain+FAISS |
# |--------|-------------|------------|-----------------|
# | Recall@1  | 45.0% | 42.0% | 40.0% |
# | Recall@5  | 78.0% | 74.0% | 72.0% |
# | MRR       | 0.542 | 0.498 | 0.485 |
# | Avg Latency (ms) | 45.2 | 52.3 | 48.7 |
```

### Benchmark with Vietnamese Queries

```bash
python run_benchmark.py --vietnamese --output results/vi_benchmark.json
```

### Analyze Results

```bash
# Text summary
python analyze_results.py results/benchmark.json

# HTML report with charts
python analyze_results.py results/benchmark.json --format html --output report.html

# Compare two runs
python analyze_results.py results/new.json --compare results/baseline.json
```

### Benchmark Specific Systems

```bash
# Only MetadataHub and LlamaIndex
python run_benchmark.py --systems metadatahub llamaindex

# Only LangChain
python run_benchmark.py --systems langchain
```

### Custom Corpus

```bash
# Use your own corpus
python run_benchmark.py --corpus /path/to/your/documents
```

## Adding New Systems

1. Create a new runner in `systems/`:

```python
from .base_runner import BaseRunner, IndexStats, SearchResult

class MyNewRunner(BaseRunner):
    def __init__(self):
        super().__init__("MyNewSystem")
    
    def index(self, corpus_path: str) -> IndexStats:
        # Index the corpus
        ...
        return IndexStats(...)
    
    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        # Search and return results
        ...
    
    def get_index_size_mb(self) -> float:
        # Return index size
        ...
    
    def cleanup(self) -> None:
        # Clean up resources
        ...
```

2. Register in `systems/__init__.py`
3. Add to `run_benchmark.py`

## Fair Comparison Notes

To ensure fair comparison, all systems use:

1. **Same embedding model**: `sentence-transformers/all-MiniLM-L6-v2`
2. **Same corpus**: All systems index the same documents
3. **Same queries**: Evaluated on identical queries
4. **Same hardware**: Run on the same machine
5. **Cold start**: Each system starts fresh for indexing

## Interpreting Results

### Good Recall@5 Scores
- **> 80%**: Excellent - system reliably finds relevant docs
- **60-80%**: Good - most queries successful
- **40-60%**: Fair - room for improvement
- **< 40%**: Poor - significant retrieval issues

### Good MRR Scores
- **> 0.6**: Excellent - relevant docs typically in top 2
- **0.4-0.6**: Good - relevant docs usually in top 3-4
- **0.2-0.4**: Fair - relevant docs often buried
- **< 0.2**: Poor - first relevant result typically far down

### Latency Expectations
- **< 50ms**: Excellent for interactive use
- **50-200ms**: Acceptable for most applications
- **> 500ms**: May impact user experience

## Contributing

To add more test queries:

1. Edit `ground_truth.json`
2. Add query with all required fields
3. Run benchmark to verify

To improve corpus diversity:

1. Add documents to appropriate `corpus/` subdirectory
2. Update `ground_truth.json` with queries for new docs
3. Re-run benchmark

## License

MIT License - see main repository.
