# MetadataHub Search Skill

Search and retrieve information from the user's indexed document library — reports, spreadsheets, code, notes, and more.

## When to Use

Use this skill when you need to find information across the user's documents. MetadataHub uses a **two-tier retrieval** system:

- **Tier 1 (Vector Search):** Fast semantic search to identify the top matching *source documents*
- **Tier 2 (Tree Retrieval):** Deep, structured navigation within a specific source to find the exact section

## Two-Step Retrieval

### Step 1: Find Relevant Sources

Run `search.py` with the user's query to get ranked source documents:

```bash
python skills/metadatahub/search.py "What was Q3 revenue?" --top-k 5
```

Returns the top-5 matching documents with summaries and similarity scores. This tells you *which documents* likely have the answer.

### Step 2: Deep Retrieve from a Source

Once you know the source, load its tree index to reason about which section to read:

```bash
python skills/metadatahub/deep_retrieve.py src_a1b2c3
```

This shows the hierarchical tree structure with summaries at every level. **Reason over the tree nodes** to decide which section(s) contain the answer. Then read the actual content:

```bash
python skills/metadatahub/read_source.py src_a1b2c3 n2.1
```

## Command Reference

### search.py — Vector Search (Tier 1)
```bash
python skills/metadatahub/search.py "<query>" [--top-k N] [--store PATH] [--json]
```

### deep_retrieve.py — Tree Navigation (Tier 2)
```bash
python skills/metadatahub/deep_retrieve.py <source_id> [--node <node_id>] [--json] [--summary]
```

### read_source.py — Content Retrieval
```bash
python skills/metadatahub/read_source.py <source_id> <node_id> [--json]
python skills/metadatahub/read_source.py <source_id> --all
python skills/metadatahub/read_source.py <source_id> --file <relative_path>
```

## Important Notes

- Always start with **Step 1** (vector search) to find the right source
- Only go to **Step 2** when you need specific details from within a document
- Tree summaries are often sufficient — you don't always need the full content
- For Excel/tabular sources, tree nodes include schema info and sample data
- The `--json` flag on any command gives structured output for programmatic use
- Vector search is fully local (no API calls needed)
