"""AI Sampling module.

Sends file samples to Claude to get an indexing strategy back.
This is the "intelligence" of the ingest pipeline — Claude decides
how each document should be processed based on a sample.
"""

import json
from pathlib import Path
from typing import Optional

from scripts.claude_client import ClaudeClient
from scripts.converters import get_sample as converter_get_sample


SAMPLING_SYSTEM_PROMPT = """You are a document analysis expert working for MetadataHub, a knowledge indexing system.

Your job: examine a sample of a document and decide the best indexing strategy.

You MUST respond with valid JSON only — no explanations, no markdown, just the JSON object.

The JSON schema you must follow:
{
  "doc_nature": "<string: what kind of document this is, e.g. financial_report, api_docs, meeting_notes, sales_data, source_code, etc.>",
  "has_structure": <boolean: does the document have clear hierarchical structure?>,
  "recommended_approach": "<one of: tree_index, schema_index, symbol_index, chunk_embed>",
  "key_sections": ["<list of main sections or topics found>"],
  "estimated_nodes": <integer: estimated number of tree nodes for indexing>,
  "special_handling": "<string or null: any special processing notes>",
  "summary": "<string: 1-2 sentence summary of the document's content and purpose>",
  "tags": ["<list of 3-5 topic tags>"]
}

Strategy decision guide:
- tree_index: Documents with hierarchical structure (headings, ToC, sections). PDFs with chapters, structured markdown, documentation.
- schema_index: Tabular/spreadsheet data. Excel files, CSVs with consistent columns.
- symbol_index: Code files with functions, classes, imports.
- chunk_embed: Flat unstructured text without clear sections. Notes, transcripts, plain text."""


SAMPLING_USER_TEMPLATE = """Analyze this document sample and return the indexing strategy as JSON.

**File info:**
- Filename: {filename}
- Type: {file_type}
- Category: {category}
- Size: {size_kb} KB

**Document sample:**
```
{sample}
```

Respond with the strategy JSON only."""


def extract_sample(filepath: Path, file_type: str, category: str = "unknown") -> str:
    """Extract an appropriate sample from a file for AI analysis.

    Uses type-specific extractors when available, falls back to raw text.
    """
    sample = converter_get_sample(filepath, file_type, category)
    if sample is None:
        # Last resort: raw bytes as text
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(2000)
        except Exception:
            sample = "[Could not read file content]"
    return sample


def build_sampling_prompt(file_card: dict, sample: str) -> str:
    """Build the prompt to send to Claude for strategy analysis."""
    return SAMPLING_USER_TEMPLATE.format(
        filename=file_card["filename"],
        file_type=file_card["type"],
        category=file_card["category"],
        size_kb=file_card["size_kb"],
        sample=sample,
    )


def request_strategy(client: ClaudeClient, file_card: dict, sample: str) -> dict:
    """Send a sample to Claude and get an indexing strategy back.

    Args:
        client: Configured ClaudeClient instance.
        file_card: File card dict from detect.py.
        sample: Extracted text sample.

    Returns:
        Strategy dict with doc_nature, recommended_approach, etc.
        On failure, returns a fallback strategy.
    """
    prompt = build_sampling_prompt(file_card, sample)
    result = client.send_json_message(
        prompt=prompt,
        system=SAMPLING_SYSTEM_PROMPT,
        max_tokens=1024,
    )

    if result.get("parsed"):
        strategy = result["parsed"]
        # Validate required fields
        required = ["doc_nature", "recommended_approach", "summary"]
        if all(k in strategy for k in required):
            return strategy

    # Fallback: use heuristic strategy
    return _fallback_strategy(file_card)


def _fallback_strategy(file_card: dict) -> dict:
    """Generate a heuristic strategy when Claude is unavailable."""
    category = file_card.get("category", "unknown")
    file_type = file_card.get("type", "unknown")

    approach_map = {
        "document": "tree_index",
        "spreadsheet": "schema_index",
        "code": "symbol_index",
        "text": "tree_index",
        "web": "tree_index",
    }

    approach = approach_map.get(category, "chunk_embed")

    return {
        "doc_nature": f"{category}_{file_type}",
        "has_structure": category in ("document", "spreadsheet", "code", "text"),
        "recommended_approach": approach,
        "key_sections": [],
        "estimated_nodes": 5,
        "special_handling": "Fallback strategy — Claude was not available for sampling",
        "summary": f"File: {file_card['filename']} ({file_type}, {file_card['size_kb']} KB)",
        "tags": [category, file_type],
    }


def sample_file(
    filepath: Path,
    file_card: dict,
    client: Optional[ClaudeClient] = None,
) -> dict:
    """Full sampling pipeline for a single file.

    1. Extract sample from file
    2. Send to Claude (or use fallback)
    3. Return updated file card with strategy

    Args:
        filepath: Path to the file.
        file_card: File card from detect.py.
        client: ClaudeClient instance. If None, uses fallback strategy.

    Returns:
        Updated file card with 'strategy' and 'sampled' fields set.
    """
    filepath = Path(filepath)
    sample = extract_sample(filepath, file_card["type"], file_card.get("category", "unknown"))

    if client is not None:
        try:
            strategy = request_strategy(client, file_card, sample)
        except Exception as e:
            print(f"  Warning: Claude sampling failed for {file_card['filename']}: {e}")
            strategy = _fallback_strategy(file_card)
    else:
        strategy = _fallback_strategy(file_card)

    # Update the file card
    file_card["sampled"] = True
    file_card["strategy"] = strategy

    return file_card
