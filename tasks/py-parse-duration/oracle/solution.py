import re

_PATTERN = re.compile(r"(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")
_SECONDS = (604800, 86400, 3600, 60, 1)


def parse_duration(text):
    if not isinstance(text, str) or not text:
        raise ValueError("invalid duration")
    match = _PATTERN.fullmatch(text)
    if match is None:
        raise ValueError("invalid duration")
    return sum(int(g) * s for g, s in zip(match.groups(), _SECONDS, strict=True) if g is not None)
