---
name: metadatahub-search
description: Ingest files and search MetadataHub knowledge index using natural language. Triggers on Vietnamese/English queries like "nộp file này", "thêm vào knowledge base", "tìm thông tin về...", "search for...", "tìm trong tài liệu", "file nào nói về...".
---

# MetadataHub

Natural language interface for knowledge index.

## Usage

```bash
python3 scripts/mhub.py "<natural language query>"
```

## Examples

**Nộp file:**
- `"nộp file report.pdf"` → ingest report.pdf
- `"thêm folder docs/ vào index"` → ingest docs/
- `"index tất cả file trong ./data"` → ingest ./data

**Tìm kiếm:**
- `"tìm thông tin về doanh thu Q3"` → search "doanh thu Q3"
- `"file nào nói về budget?"` → search "budget"
- `"search revenue breakdown"` → search "revenue breakdown"

**Xem chi tiết:**
- `"xem cấu trúc src_abc123"` → retrieve tree
- `"đọc node n1 của src_abc123"` → read content

## Store

Default: `~/.metadatahub/store`
