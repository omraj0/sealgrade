import re


def parse_duration(text):
    # Plausible but wrong: accepts units in any order and repeated, and ignores junk between them.
    units = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}
    parts = re.findall(r"(\d+)([wdhms])", text)
    if not parts:
        raise ValueError("invalid duration")
    return sum(int(n) * units[u] for n, u in parts)
