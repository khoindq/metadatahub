"""File type detection and classification.

Classifies files using three signals:
1. File extension mapping
2. Magic bytes (file signatures)
3. First 500 bytes content heuristics

Produces a "file card" dict for each file.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional


# Extension → type mapping
EXTENSION_MAP = {
    # Documents
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".rtf": "rtf",
    ".odt": "odt",
    # Spreadsheets
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".csv": "csv",
    ".tsv": "tsv",
    ".ods": "ods",
    # Markdown / text
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".rst": "rst",
    # Code
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c_header",
    ".hpp": "cpp_header",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".xml": "xml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    # Images (for OCR path)
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".webp": "image",
    # Archives (skip)
    ".zip": "archive",
    ".tar": "archive",
    ".gz": "archive",
}

# Magic bytes → type (prefix matching)
MAGIC_BYTES = {
    b"%PDF": "pdf",
    b"PK\x03\x04": "zip_based",  # XLSX, DOCX, etc. are ZIP-based
    b"\xd0\xcf\x11\xe0": "ole",  # Legacy .doc, .xls
    b"\x89PNG": "image",
    b"\xff\xd8\xff": "image",  # JPEG
    b"GIF8": "image",
}

# Categories for grouping
TYPE_CATEGORIES = {
    "document": {"pdf", "docx", "doc", "rtf", "odt"},
    "spreadsheet": {"xlsx", "xls", "csv", "tsv", "ods"},
    "text": {"markdown", "text", "rst"},
    "code": {
        "python", "javascript", "typescript", "java", "go", "rust",
        "ruby", "php", "c", "cpp", "c_header", "cpp_header", "csharp",
        "swift", "kotlin", "shell",
    },
    "web": {"html", "css", "xml", "json", "yaml", "toml"},
    "image": {"image"},
    "archive": {"archive"},
}


def _generate_id(filepath: Path) -> str:
    """Generate a deterministic source ID from file path + size."""
    stat = filepath.stat()
    key = f"{filepath.name}:{stat.st_size}:{stat.st_mtime_ns}"
    h = hashlib.sha256(key.encode()).hexdigest()[:10]
    return f"src_{h}"


def _detect_by_extension(filepath: Path) -> Optional[str]:
    ext = filepath.suffix.lower()
    return EXTENSION_MAP.get(ext)


def _detect_by_magic(header: bytes) -> Optional[str]:
    for magic, file_type in MAGIC_BYTES.items():
        if header.startswith(magic):
            return file_type
    return None


def _detect_by_content(header: bytes, ext_type: Optional[str]) -> Optional[str]:
    """Heuristic detection from first 500 bytes content."""
    if not header:
        return None
    try:
        text = header.decode("utf-8", errors="ignore").strip()
    except Exception:
        return None

    # CSV heuristic: lines with consistent comma/tab counts
    lines = text.split("\n")[:5]
    if len(lines) >= 2:
        comma_counts = [line.count(",") for line in lines if line.strip()]
        if comma_counts and all(c == comma_counts[0] and c >= 2 for c in comma_counts):
            return "csv"

        tab_counts = [line.count("\t") for line in lines if line.strip()]
        if tab_counts and all(c == tab_counts[0] and c >= 2 for c in tab_counts):
            return "tsv"

    # Markdown heuristic: starts with # heading
    if text.startswith("#") or text.startswith("---\n"):
        return "markdown"

    # JSON heuristic
    if text.startswith("{") or text.startswith("["):
        return "json"

    # XML/HTML heuristic
    if text.startswith("<?xml") or text.startswith("<!DOCTYPE") or text.startswith("<html"):
        if ext_type in ("html", "xml"):
            return ext_type
        return "xml"

    return None


def get_category(file_type: str) -> str:
    """Return the category for a file type."""
    for category, types in TYPE_CATEGORIES.items():
        if file_type in types:
            return category
    return "unknown"


def _resolve_type(ext_type: Optional[str], magic_type: Optional[str], content_type: Optional[str]) -> str:
    """Resolve final type from the three signals.

    Priority: magic bytes can override extension for ZIP-based formats,
    otherwise extension wins, with content as fallback.
    """
    # ZIP-based magic: refine using extension (xlsx vs docx)
    if magic_type == "zip_based" and ext_type in ("xlsx", "docx", "odt", "ods"):
        return ext_type

    # Extension is generally most reliable
    if ext_type:
        return ext_type

    # Magic bytes next
    if magic_type and magic_type not in ("zip_based", "ole"):
        return magic_type

    # Content heuristics
    if content_type:
        return content_type

    return "unknown"


def detect_file(filepath: Path) -> dict:
    """Detect file type and produce a file card.

    Returns a dict with:
        id, filename, path, type, category, size_kb,
        sampled (bool), strategy (None until AI sampling)
    """
    filepath = Path(filepath).resolve()
    if not filepath.is_file():
        raise FileNotFoundError(f"Not a file: {filepath}")

    size_bytes = filepath.stat().st_size
    size_kb = round(size_bytes / 1024, 1)

    # Read header for magic bytes + content heuristics
    with open(filepath, "rb") as f:
        header = f.read(500)

    ext_type = _detect_by_extension(filepath)
    magic_type = _detect_by_magic(header)
    content_type = _detect_by_content(header, ext_type)

    file_type = _resolve_type(ext_type, magic_type, content_type)
    category = get_category(file_type)

    card = {
        "id": _generate_id(filepath),
        "filename": filepath.name,
        "path": str(filepath),
        "type": file_type,
        "category": category,
        "size_kb": size_kb,
        "sampled": False,
        "strategy": None,
    }

    # Add type-specific metadata
    if file_type == "pdf":
        card["pages"] = None  # Filled by converter
    elif category == "spreadsheet":
        card["sheets"] = None  # Filled by converter

    return card


def detect_directory(dirpath: Path) -> list[dict]:
    """Detect all files in a directory (non-recursive by default)."""
    dirpath = Path(dirpath).resolve()
    if not dirpath.is_dir():
        raise NotADirectoryError(f"Not a directory: {dirpath}")

    cards = []
    for entry in sorted(dirpath.iterdir()):
        if entry.is_file() and not entry.name.startswith("."):
            try:
                cards.append(detect_file(entry))
            except Exception as e:
                print(f"Warning: could not detect {entry.name}: {e}")
    return cards
