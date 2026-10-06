Create `/work/solution.py` that defines `rle_encode(text: str) -> str`.

Run-length encoding replaces each run of identical characters with the character followed by the
length of the run, always, even when the run has length 1: `"aaabcc"` becomes `"a3b1c2"` and
the empty string becomes the empty string.

Raise `ValueError` if `text` is not a string or if it contains any digit.

Use only the Python standard library.
