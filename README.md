# MetadataHub

A file-based, open-source knowledge index for feeding AI agents. Combines fast vector search (source detection) with deep reasoning-based tree search (precise extraction).

## Features

- **File-based everything** — No servers, no Docker. Just JSON + FAISS files
- **AI-first ingestion** — Claude samples documents and decides indexing strategy
- **Two-tier retrieval** — Vector search → which source? Tree reasoning → which section?
- **Skills-based** — Agent consumes via skill files, not MCP

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Drop files into inbox/
cp your_documents/* inbox/

# Run ingestion
python scripts/ingest.py ./inbox/

# Query via skill
python skills/metadatahub/search.py "your query"
```

## Status

🚧 Under development — Phase 1

## License

MIT
