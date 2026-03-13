import os
import shutil
import sys
import textwrap


RESET = "\033[0m"
STYLES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
}
COLORS = {
    "gold": "\033[38;5;220m",
    "cyan": "\033[38;5;117m",
    "green": "\033[38;5;114m",
    "red": "\033[38;5;203m",
    "blue": "\033[38;5;75m",
    "magenta": "\033[38;5;177m",
    "gray": "\033[38;5;245m",
    "silver": "\033[38;5;252m",
    "parchment": "\033[38;5;230m",
    "quote": "\033[38;5;186m",
}


def color_enabled() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def style(text: str, color: str | None = None, bold: bool = False, dim: bool = False, italic: bool = False) -> str:
    if not color_enabled():
        return text

    parts = []
    if bold:
        parts.append(STYLES["bold"])
    if dim:
        parts.append(STYLES["dim"])
    if italic:
        parts.append(STYLES["italic"])
    if color:
        parts.append(COLORS[color])
    return "".join(parts) + text + RESET


def banner(title: str) -> str:
    line = "═" * max(20, len(title) + 6)
    return f"{style(line, 'gold', bold=True)}\n{style(f'  {title}  ', 'gold', bold=True)}\n{style(line, 'gold', bold=True)}"


def section(title: str) -> str:
    return style(f"\n[{title}]", "cyan", bold=True)


def speaker(name: str, color: str) -> str:
    return style(f"{name}:", color, bold=True)


def bullet(text: str) -> str:
    return f"{style('•', 'gold', bold=True)} {text}"


def prompt_marker() -> str:
    return style("»", "green", bold=True) + " "


def terminal_width(default: int = 100) -> int:
    return max(40, shutil.get_terminal_size(fallback=(default, 24)).columns - 2)


def wrap_text(text: str, width: int | None = None) -> str:
    wrap_width = width or terminal_width()
    paragraphs = text.splitlines()
    wrapped = []
    for paragraph in paragraphs:
        if not paragraph.strip():
            wrapped.append("")
            continue
        wrapped.append(textwrap.fill(paragraph, width=wrap_width, break_long_words=False, break_on_hyphens=False))
    return "\n".join(wrapped)
