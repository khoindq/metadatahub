"""File converters registry.

Maps file types to their converter modules.
"""

from pathlib import Path
from typing import Optional

from scripts.converters import pdf_converter, xlsx_converter, md_converter

# type → converter module
CONVERTERS = {
    "pdf": pdf_converter,
    "xlsx": xlsx_converter,
    "markdown": md_converter,
}

# Category → converter (fallback)
CATEGORY_CONVERTERS = {
    "text": md_converter,  # Use markdown converter for plain text too
}


def get_converter(file_type: str, category: str = "unknown"):
    """Get the appropriate converter module for a file type."""
    if file_type in CONVERTERS:
        return CONVERTERS[file_type]
    if category in CATEGORY_CONVERTERS:
        return CATEGORY_CONVERTERS[category]
    return None


def convert_file(filepath: Path, file_type: str, category: str = "unknown",
                 output_dir: Optional[Path] = None) -> Optional[dict]:
    """Convert a file using the appropriate converter."""
    converter = get_converter(file_type, category)
    if converter is None:
        return None
    return converter.convert(filepath, output_dir=output_dir)


def get_sample(filepath: Path, file_type: str, category: str = "unknown",
               **kwargs) -> Optional[str]:
    """Get a sample from a file using the appropriate converter."""
    converter = get_converter(file_type, category)
    if converter is None:
        # Fallback: read first 2000 bytes as text
        try:
            text = filepath.read_text(encoding="utf-8", errors="ignore")[:2000]
            return text
        except Exception:
            return None
    return converter.get_sample(filepath, **kwargs)
