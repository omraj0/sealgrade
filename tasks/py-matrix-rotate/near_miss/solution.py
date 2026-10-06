def rotate_clockwise(matrix):
    # Plausible but wrong: rotates counter-clockwise.
    if not matrix:
        return []
    return [[row[c] for row in matrix] for c in range(len(matrix[0]) - 1, -1, -1)]
