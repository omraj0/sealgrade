def two_sum(numbers, target):
    # Plausible but wrong: allows the same element to be used twice.
    for j in range(len(numbers)):
        for i in range(j + 1):
            if numbers[i] + numbers[j] == target:
                return [i, j]
    return None
