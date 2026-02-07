# Changelog

All notable changes to MetadataHub will be documented in this file.

## [0.1.0] - 2025-02-07

### Added

#### Phase 1 - Core Modules
- `scripts/config.py` - Configuration dataclass with OAuth and ingest settings
- `scripts/detect.py` - 3-signal file classifier (extension + magic bytes + content)
- `scripts/converters/` - File converters for PDF, XLSX, Markdown
- `scripts/claude_client.py` - Claude API client with OAuth/API key auth
- `scripts/sample.py` - AI sampling with strategy response
- `scripts/catalog.py` - catalog.json CRUD operations

#### Phase 2 - Indexing
- `scripts/build_tree.py` - Hierarchical tree index builder
- `scripts/build_vectors.py` - FAISS vector index with sentence-transformers
- `scripts/ingest.py` - Full pipeline CLI

#### Phase 3 - Retrieval Skill
- `skills/metadatahub/search.py` - Tier 1 vector similarity search
- `skills/metadatahub/deep_retrieve.py` - Tier 2 tree navigation
- `skills/metadatahub/read_source.py` - Content retrieval by node
- `skills/metadatahub/SKILL.md` - Agent instructions

#### Phase 4 - Polish
- `scripts/incremental.py` - Incremental re-indexing (only new/changed files)
- `scripts/link_sources.py` - Cross-source linking via embeddings + keywords
- `--incremental` flag for ingest CLI
- `requirements.txt` - Dependency specifications
- Comprehensive README with usage examples

### Tests
- 140 tests passing across all phases

---

## Roadmap

### [0.2.0] - Planned
- Quality scoring for tree nodes
- Watch mode for automatic re-indexing
- Multi-language document support
- Plugin architecture for custom converters
