# MetadataHub 📚

A file-based knowledge index system for AI agents with hybrid vector + tree retrieval.

## Overview

MetadataHub indexes your documents (PDFs, Excel, Markdown, Code) into a searchable knowledge base. AI agents can then search semantically and drill down into document structure.

```
Your Files → Ingest → [Vector Index + Tree Index] → Search → Answers
```

## Features

- **🔍 Semantic Search** - Find relevant documents using natural language
- **🌳 Tree Navigation** - Browse document structure (sections, sheets, symbols)
- **📄 Multi-format Support** - PDF, XLSX, Markdown, Python, and more
- **🤖 AI-Powered** - Claude API for smart summaries and tagging
- **📦 No Server Required** - Pure file-based, runs locally

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Ingest Files

```bash
python -m scripts.ingest ./your-documents/ --store ~/.metadatahub/store
```

### 3. Search

```bash
python skills/metadatahub-search/scripts/mhub.py "your question here"
```

## Architecture

```
metadatahub/
├── scripts/                    # Core modules
│   ├── config.py              # Configuration dataclass
│   ├── detect.py              # File type detection (ext + magic + content)
│   ├── sample.py              # AI sampling for summaries/tags
│   ├── catalog.py             # Catalog CRUD operations
│   ├── build_tree.py          # Hierarchical tree index builder
│   ├── build_vectors.py       # FAISS vector index (MiniLM-L6-v2)
│   ├── ingest.py              # Full pipeline CLI
│   ├── claude_client.py       # Claude API client
│   └── converters/            # File converters
│       ├── pdf_converter.py
│       ├── xlsx_converter.py
│       └── md_converter.py
│
├── skills/
│   └── metadatahub/           # Retrieval skill for agents
│       ├── search.py          # Tier 1: Vector similarity search
│       ├── deep_retrieve.py   # Tier 2: Tree navigation
│       ├── read_source.py     # Content retrieval
│       └── SKILL.md           # Agent instructions
│
└── dist/
    └── metadatahub-search.skill  # Packaged OpenClaw skill
```

## Usage

### Ingest Pipeline

```bash
# Basic usage
python -m scripts.ingest ./documents/

# Custom store location
python -m scripts.ingest ./documents/ --store /path/to/store

# Skip vector building (faster)
python -m scripts.ingest ./documents/ --no-vectors

# Quiet mode
python -m scripts.ingest ./documents/ --quiet
```

### Search & Retrieve

```python
from skills.metadatahub.search import search
from skills.metadatahub.deep_retrieve import retrieve
from skills.metadatahub.read_source import read

# Step 1: Search for relevant sources
results = search("Q3 revenue breakdown", store_path="./store")
# Returns: [{"id": "src_abc123", "filename": "report.pdf", "score": 0.85}, ...]

# Step 2: Get document structure
tree = retrieve("src_abc123", store_path="./store")
# Returns tree with sections/sheets/symbols

# Step 3: Read specific content
content = read("src_abc123", "n2", store_path="./store")
# Returns actual text/data from that node
```

### CLI Tool

```bash
# Search
python mhub.py "doanh thu Q3"

# View document structure
python mhub.py --retrieve src_abc123

# Read specific node
python mhub.py --read src_abc123 n2
```

### Natural Language (Vietnamese + English)

```bash
python mhub.py "tìm thông tin về revenue"
python mhub.py "file nào nói về budget?"
python mhub.py "nộp file report.pdf"
```

## Store Structure

```
~/.metadatahub/store/
├── catalog.json           # Source metadata
├── config.json            # Store configuration
├── inbox/                 # Original files (optional)
├── converted/             # Extracted content
│   └── src_abc123/
│       ├── section_1.md
│       └── sheet_data.json
├── tree_index/            # Hierarchical trees
│   └── src_abc123.json
└── vector_store/          # FAISS index
    ├── index.faiss
    └── id_map.json
```

## Supported File Types

| Type | Extensions | Indexing Strategy |
|------|------------|-------------------|
| PDF | `.pdf` | Page extraction, section detection |
| Excel | `.xlsx`, `.xls` | Sheet-by-sheet, schema extraction |
| Markdown | `.md` | Header-based sections |
| Python | `.py` | Symbol extraction (classes, functions) |
| Text | `.txt`, `.csv` | Full-text indexing |

## Configuration

### Environment Variables

```bash
# Claude API (optional, for AI summaries)
export ANTHROPIC_API_KEY=your_key

# HuggingFace (optional, for faster model downloads)
export HF_TOKEN=your_token
```

### Config File

```python
from scripts.config import Config

config = Config(
    store_root="~/.metadatahub/store",
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    embedding_dim=384,
    use_claude=True
)
```

## OpenClaw Skill

Install the skill for use with OpenClaw:

```bash
# Copy to OpenClaw skills directory
cp -r skills/metadatahub-search /path/to/openclaw/skills/

# Or use the packaged skill
unzip dist/metadatahub-search.skill -d /path/to/openclaw/skills/
```

Then ask questions naturally:
- "Doanh thu Q3 là bao nhiêu?"
- "File nào có thông tin về Cloud Services?"
- "Tìm trong tài liệu về budget planning"

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Test Coverage

- Phase 1 (Core): 63 tests
- Phase 2 (Indexing): 57 tests  
- Phase 3 (Retrieval): 20 tests
- **Total: 140 tests passing**

## Roadmap

- [x] Phase 1: Core modules (detect, convert, sample, catalog)
- [x] Phase 2: Indexing (tree builder, vector index, ingest CLI)
- [x] Phase 3: Retrieval skill (search, deep_retrieve, read_source)
- [ ] Phase 4: Polish (incremental re-indexing, cross-source linking)

## License

MIT

## Author

Built with ❤️ by Khoi & Claude
