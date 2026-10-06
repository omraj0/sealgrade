Create `/work/solution.py` that defines `parse_duration(text: str) -> int`.

The text is a sequence of numbers with unit suffixes `w` (weeks), `d` (days), `h` (hours),
`m` (minutes) and `s` (seconds), for example `"1h30m"` or `"2d"` or `"1w2d3h4m5s"`. Return the total
number of seconds as an integer.

Each unit may appear at most once and units must appear from largest to smallest. Numbers are
non-negative integers. No whitespace, no signs, no decimals.

Raise `ValueError` for the empty string, anything that does not follow these rules, and
non-string input.

Use only the Python standard library.
