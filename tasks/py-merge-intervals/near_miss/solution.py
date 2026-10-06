def merge_intervals(intervals):
    # Plausible but wrong: intervals that only touch are left separate.
    merged = []
    for start, end in sorted(([s, e] for s, e in intervals), key=lambda pair: pair[0]):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
