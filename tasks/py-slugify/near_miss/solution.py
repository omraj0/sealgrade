import re


def slugify(text: str) -> str:
    # Plausible but wrong: no accent folding and no trimming of edge hyphens.
    return re.sub(r"[^a-z0-9]+", "-", text.lower())
