"""Markdown pass-through converter with structure markers.

Preserves original content but adds structural markers for headings,
code blocks, and lists to aid tree index generation.
"""

import re
from pathlib import Path
from typing import Optional


def convert(filepath: Path, output_dir: Optional[Path] = None) -> dict:
    """Convert a Markdown file — pass-through with structure annotation.

    Args:
        filepath: Path to the .md file.
        output_dir: Directory to write converted file.

    Returns:
        dict with keys:
            text: the markdown content with structure markers
            sections: list of section dicts (title, level, line_start, line_end)
            output_files: list of written file paths
    """
    filepath = Path(filepath)
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")

    sections = _extract_sections(lines)

    result = {
        "text": content,
        "sections": sections,
        "output_files": [],
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write full content
        full_path = output_dir / "full.md"
        full_path.write_text(content, encoding="utf-8")
        result["output_files"].append(str(full_path))

        # Write per-section files if there are sections
        for section in sections:
            section_lines = lines[section["line_start"]:section["line_end"]]
            section_text = "\n".join(section_lines)
            safe_title = re.sub(r'[^\w\s-]', '', section["title"]).strip()
            safe_title = re.sub(r'\s+', '_', safe_title).lower()[:50]
            section_path = output_dir / f"section_{safe_title}.md"
            section_path.write_text(section_text, encoding="utf-8")
            result["output_files"].append(str(section_path))

    return result


def _extract_sections(lines: list[str]) -> list[dict]:
    """Parse markdown headings into a section list."""
    sections = []
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')

    heading_positions = []
    for i, line in enumerate(lines):
        m = heading_pattern.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            heading_positions.append((i, level, title))

    for idx, (line_num, level, title) in enumerate(heading_positions):
        if idx + 1 < len(heading_positions):
            end = heading_positions[idx + 1][0]
        else:
            end = len(lines)

        sections.append({
            "title": title,
            "level": level,
            "line_start": line_num,
            "line_end": end,
        })

    return sections


def get_sample(filepath: Path, max_chars: int = 2000) -> str:
    """Extract a sample from the Markdown file for AI sampling.

    Returns the beginning of the file plus a table of contents.
    """
    filepath = Path(filepath)
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")

    sections = _extract_sections(lines)

    # Build a ToC
    toc_parts = ["[Table of Contents]"]
    for section in sections:
        indent = "  " * (section["level"] - 1)
        toc_parts.append(f"{indent}- {section['title']}")

    toc = "\n".join(toc_parts)

    # First N chars of content
    preview = content[:max_chars]
    if len(content) > max_chars:
        preview += "\n[...truncated]"

    return f"{toc}\n\n[Content Preview]\n{preview}"
