Create `/work/solution.py` that defines `merge_intervals(intervals: list[list[int]]) -> list[list[int]]`.

Each interval is `[start, end]` with `start <= end`. Merge every group of intervals that overlap or
merely touch (`[1, 3]` and `[3, 5]` become `[1, 5]`) and return the merged intervals sorted by start.

The input may be empty and is not necessarily sorted. Do not modify the input list.

Use only the Python standard library.
