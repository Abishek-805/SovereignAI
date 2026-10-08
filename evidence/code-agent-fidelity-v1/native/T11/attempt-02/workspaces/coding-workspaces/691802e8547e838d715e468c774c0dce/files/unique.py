def stable_unique(values):
    seen = set()
    result = []
    for v in values:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result
def checksum(values):
    return sum(values)
