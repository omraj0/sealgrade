def two_sum(numbers, target):
    for j in range(len(numbers)):
        for i in range(j):
            if numbers[i] + numbers[j] == target:
                return [i, j]
    return None
