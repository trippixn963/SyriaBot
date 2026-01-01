"""
SyriaBot - Text Utilities
=========================

Shared text processing functions.
"""

from PIL import ImageFont


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """
    Wrap text to fit within max_width, returning list of lines.

    Args:
        text: The text to wrap
        font: PIL font to use for measuring
        max_width: Maximum width in pixels

    Returns:
        List of wrapped lines
    """
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]

        if line_width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines if lines else [text]
