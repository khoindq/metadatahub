"""Excel → Markdown/JSON converter using openpyxl.

Extracts sheet names, headers, sample rows, and basic stats.
Produces:
1. Markdown per sheet for tree indexing (enables deeper navigation)
2. JSON per sheet for structured data access
"""

from pathlib import Path
from typing import Optional

from openpyxl import load_workbook


def convert(filepath: Path, output_dir: Optional[Path] = None) -> dict:
    """Convert an Excel file to Markdown + JSON.

    Args:
        filepath: Path to the .xlsx file.
        output_dir: Directory to write converted files.

    Returns:
        dict with keys:
            sheets: list of sheet info dicts
            output_files: list of written file paths
            markdown_content: combined markdown for all sheets
    """
    import json

    filepath = Path(filepath)
    wb = load_workbook(filepath, read_only=True, data_only=True)

    sheets = []
    output_files = []
    markdown_parts = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if not rows:
            sheets.append({
                "name": sheet_name,
                "headers": [],
                "row_count": 0,
                "sample_rows": [],
                "column_count": 0,
            })
            markdown_parts.append(f"# Sheet: {sheet_name}\n\n(empty sheet)\n")
            continue

        # First row as headers
        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]

        # Build markdown table
        md_lines = [f"# Sheet: {sheet_name}\n"]
        
        # Add metadata hint
        md_lines.append(f"_Columns: {', '.join(headers)}_\n")
        
        # Table header
        md_lines.append("| " + " | ".join(headers) + " |")
        md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        
        # Table rows (all data)
        row_labels = []
        for row in data_rows:
            cells = []
            for i, val in enumerate(row):
                cell_str = _serialize_value(val)
                cells.append(str(cell_str) if cell_str is not None else "")
            md_lines.append("| " + " | ".join(cells) + " |")
            # Track first column as row label (for hints)
            if cells:
                row_labels.append(cells[0])
        
        md_lines.append("")  # blank line between sheets
        
        # Sample rows for JSON (first 5)
        sample_rows = []
        for row in data_rows[:5]:
            sample_row = {}
            for header, val in zip(headers, row):
                sample_row[header] = _serialize_value(val)
            sample_rows.append(sample_row)

        sheet_info = {
            "name": sheet_name,
            "headers": headers,
            "row_count": len(data_rows),
            "column_count": len(headers),
            "sample_rows": sample_rows,
            "row_labels": row_labels[:20],  # For hint generation
        }
        sheets.append(sheet_info)
        markdown_parts.append("\n".join(md_lines))

    wb.close()

    markdown_content = "\n".join(markdown_parts)

    result = {
        "sheets": sheets,
        "sheet_count": len(sheets),
        "output_files": [],
        "markdown_content": markdown_content,
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write combined markdown (for tree building)
        md_path = output_dir / "full.md"
        md_path.write_text(markdown_content, encoding="utf-8")
        result["output_files"].append(str(md_path))

        # Write per-sheet JSON (for data access)
        for sheet_info in sheets:
            safe_name = sheet_info["name"].replace("/", "_").replace(" ", "_").lower()
            out_path = output_dir / f"sheet_{safe_name}.json"
            out_path.write_text(json.dumps(sheet_info, indent=2, default=str) + "\n")
            result["output_files"].append(str(out_path))
            
            # Also write per-sheet markdown
            md_sheet_path = output_dir / f"sheet_{safe_name}.md"
            sheet_md = _build_sheet_markdown(sheet_info)
            md_sheet_path.write_text(sheet_md, encoding="utf-8")
            result["output_files"].append(str(md_sheet_path))

    return result


def _build_sheet_markdown(sheet_info: dict) -> str:
    """Build markdown content for a single sheet."""
    lines = [f"# Sheet: {sheet_info['name']}\n"]
    
    headers = sheet_info.get("headers", [])
    if not headers:
        return lines[0] + "\n(empty sheet)\n"
    
    lines.append(f"_Columns: {', '.join(headers)}_\n")
    
    # Table header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    
    # Table rows from sample
    for row in sheet_info.get("sample_rows", []):
        cells = [str(row.get(h, "")) for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    
    if sheet_info.get("row_count", 0) > len(sheet_info.get("sample_rows", [])):
        remaining = sheet_info["row_count"] - len(sheet_info.get("sample_rows", []))
        lines.append(f"\n_({remaining} more rows)_")
    
    return "\n".join(lines)


def _serialize_value(val):
    """Serialize a cell value to JSON-compatible form."""
    if val is None:
        return None
    if isinstance(val, (int, float, bool)):
        return val
    return str(val)


def get_sample(filepath: Path, max_rows: int = 5) -> str:
    """Extract a sample from the Excel file for AI sampling.

    Returns sheet names + headers + first N data rows.
    """
    filepath = Path(filepath)
    wb = load_workbook(filepath, read_only=True, data_only=True)

    parts = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))

        if not rows:
            parts.append(f"[Sheet: {sheet_name}]\n(empty)")
            continue

        headers = [str(h) if h is not None else "" for h in rows[0]]
        header_line = " | ".join(headers)
        parts.append(f"[Sheet: {sheet_name}]")
        parts.append(f"Headers: {header_line}")
        parts.append(f"Total rows: {len(rows) - 1}")

        for row in rows[1:max_rows + 1]:
            vals = [str(v) if v is not None else "" for v in row]
            parts.append("  " + " | ".join(vals))

    wb.close()
    return "\n".join(parts)


def get_sheet_hint(sheet_info: dict) -> str:
    """Generate a human-readable hint for a sheet.
    
    Example: "Sheet: Revenue, contains Q1-Q4 data with Product/Cloud/Services columns"
    """
    name = sheet_info.get("name", "Unknown")
    headers = sheet_info.get("headers", [])
    row_labels = sheet_info.get("row_labels", [])
    row_count = sheet_info.get("row_count", 0)
    
    hint_parts = [f"Sheet: {name}"]
    
    # Describe row content if available
    if row_labels:
        # Summarize row labels
        if len(row_labels) <= 4:
            hint_parts.append(f"contains {', '.join(str(l) for l in row_labels)} data")
        else:
            first_few = ', '.join(str(l) for l in row_labels[:3])
            hint_parts.append(f"contains {first_few}... ({row_count} rows)")
    
    # Describe columns
    if headers:
        if len(headers) <= 5:
            hint_parts.append(f"columns: {'/'.join(headers)}")
        else:
            main_cols = '/'.join(headers[:4])
            hint_parts.append(f"columns: {main_cols} (+{len(headers)-4} more)")
    
    return ", ".join(hint_parts)
