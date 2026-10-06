import re
from collections import Counter


def word_frequency(text):
    words = (w.strip("'") for w in re.findall(r"[a-z']+", text.lower()))
    return dict(Counter(w for w in words if w))
