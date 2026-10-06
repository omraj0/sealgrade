Create `/work/solution.py` that defines `word_frequency(text: str) -> dict[str, int]`.

A word is a maximal run of ASCII letters and apostrophes, compared case-insensitively
(`"Don't"` and `"don't"` are the same word). Apostrophes at the start or end of a word are not part of
it (`"'tis"` counts as `"tis"`). Everything else separates words. Return a dictionary from each
lower-case word to the number of times it occurs.

Use only the Python standard library.
