Create `/work/solution.py` that defines `to_roman(n: int) -> str`.

It converts an integer from 1 to 3999 into a Roman numeral using standard subtractive notation
(`4` is `IV`, `9` is `IX`, `40` is `XL`, `1994` is `MCMXCIV`).

Raise `ValueError` for anything that is not an integer in that range. That includes `0`, negative
numbers, numbers above 3999, floats such as `3.5`, and strings such as `"5"`.

Use only the Python standard library.
