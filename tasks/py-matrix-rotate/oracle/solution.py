def rotate_clockwise(matrix):
    if not matrix:
        return []
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise ValueError("rows must have equal length")
    return [[matrix[r][c] for r in range(len(matrix) - 1, -1, -1)] for c in range(width)]
