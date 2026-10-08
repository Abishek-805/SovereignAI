def render(events):
    counts = {}
    for event in events:
        kind = event.get('kind')
        if kind is None or not isinstance(kind, str):
            raise ValueError("Missing or non-string kind")
        counts[kind] = counts.get(kind, 0) + 1
    lines = []
    for kind in sorted(counts.keys()):
        lines.append(f"{kind}:{counts[kind]}")
    return "\n".join(lines)
