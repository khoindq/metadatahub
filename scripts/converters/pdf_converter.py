"""PDF → text converter using pypdf.

Extracts text per page, preserves page boundaries with markers.
Returns structured output for indexing.
"""

from pathlib import Path
from typing import Optional

from pypdf import PdfReader


def convert(filepath: Path, output_dir: Optional[Path] = None) -> dict:
    """Convert a PDF to extracted text.

    Args:
        filepath: Path to the PDF file.
        output_dir: Directory to write converted text files.
                    If None, only returns the in-memory result.

    Returns:
        dict with keys:
            pages: total page count
            text: full extracted text
            page_texts: list of (page_num, text) tuples
            output_files: list of written file paths (if output_dir given)
    """
    filepath = Path(filepath)
    reader = PdfReader(filepath)
    num_pages = len(reader.pages)

    page_texts = []
    full_text_parts = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        page_num = i + 1
        page_texts.append((page_num, text))
        full_text_parts.append(f"--- PAGE {page_num} ---\n{text}")

    full_text = "\n\n".join(full_text_parts)

    result = {
        "pages": num_pages,
        "text": full_text,
        "page_texts": page_texts,
        "output_files": [],
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write full text
        full_path = output_dir / "full.txt"
        full_path.write_text(full_text, encoding="utf-8")
        result["output_files"].append(str(full_path))

        # Write page-range chunks (group pages for tree index references)
        chunk_size = 5
        for start in range(0, num_pages, chunk_size):
            end = min(start + chunk_size, num_pages)
            chunk_texts = []
            for page_num, text in page_texts[start:end]:
                chunk_texts.append(f"--- PAGE {page_num} ---\n{text}")
            chunk_path = output_dir / f"pages_{start + 1}-{end}.txt"
            chunk_path.write_text("\n\n".join(chunk_texts), encoding="utf-8")
            result["output_files"].append(str(chunk_path))

    return result


def get_sample(filepath: Path, max_pages: int = 2, max_chars: int = 2000) -> str:
    """Extract a sample from the PDF for AI sampling.

    Returns first N pages or max_chars, whichever is smaller.
    """
    filepath = Path(filepath)
    reader = PdfReader(filepath)
    parts = []
    total_chars = 0

    for i, page in enumerate(reader.pages[:max_pages]):
        text = page.extract_text() or ""
        parts.append(f"[Page {i + 1}]\n{text}")
        total_chars += len(text)
        if total_chars >= max_chars:
            break

    sample = "\n\n".join(parts)
    if len(sample) > max_chars:
        sample = sample[:max_chars] + "\n[...truncated]"
    return sample
