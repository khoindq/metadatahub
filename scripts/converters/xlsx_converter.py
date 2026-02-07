"""Excel → JSON converter using openpyxl.

Extracts sheet names, headers, sample rows, and basic stats.
Produces a structured JSON per sheet for indexing.
"""

from pathlib import Path
from typing import Optional

from openpyxl import load_workbook


def convert(filepath: Path, output_dir: Optional[Path] = None) -> dict:
    """Convert an Excel file to structured JSON.

    Args:
        filepath: Path to the .xlsx file.
        output_dir: Directory to write converted JSON files.

    Returns:
        dict with keys:
            sheets: list of sheet info dicts
            output_files: list of written file paths
    """
    import json

    filepath = Path(filepath)
    wb = load_workbook(filepath, read_only=True, data_only=True)

    sheets = []
    output_files = []

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
            continue

        # First row as headers
        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]

        # Sample rows (first 5)
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
        }
        sheets.append(sheet_info)

    wb.close()

    result = {
        "sheets": sheets,
        "sheet_count": len(sheets),
        "output_files": [],
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for sheet_info in sheets:
            safe_name = sheet_info["name"].replace("/", "_").replace(" ", "_").lower()
            out_path = output_dir / f"sheet_{safe_name}.json"
            out_path.write_text(json.dumps(sheet_info, indent=2, default=str) + "\n")
            result["output_files"].append(str(out_path))

    return result


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
