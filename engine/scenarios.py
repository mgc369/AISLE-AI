"""Curated synthetic layouts for deterministic, reproducible demonstration."""


def rect(x1, y1, x2, y2):
    return [(x, y) for x in range(x1, x2 + 1) for y in range(y1, y2 + 1)]


def unique(points):
    return [list(p) for p in sorted(set(points), key=lambda p: (p[1], p[0]))]


def scenarios():
    # Shelf islands allow distinct corridors and alternative routes.
    standard_shelves = (
        rect(4, 2, 5, 5) + rect(4, 8, 5, 10)
        + rect(9, 1, 10, 4) + rect(9, 7, 10, 11)
        + rect(14, 2, 15, 5) + rect(14, 8, 15, 10)
    )
    high_shelves = (
        rect(5, 1, 6, 4) + rect(5, 7, 6, 11)
        + rect(10, 2, 11, 5) + rect(10, 8, 11, 11)
        + rect(15, 1, 16, 4) + rect(15, 7, 16, 11)
    )
    narrow_shelves = (
        rect(3, 2, 3, 10) + rect(7, 2, 7, 10)
        + rect(11, 2, 11, 10) + rect(15, 2, 15, 10)
    )
    for shelves in (standard_shelves, high_shelves, narrow_shelves):
        assert len(set(shelves)) == len(shelves)
    return {
        'standard': {
            'name': 'Distribution center', 'description': 'Five pick locations, balanced congestion.',
            'width': 20, 'height': 13, 'start': [1, 1],
            'blocked': unique(standard_shelves),
            'hazards': unique(rect(6, 6, 8, 6) + rect(11, 6, 13, 6) + rect(16, 6, 17, 6)),
            'tasks': [[18, 2], [2, 10], [17, 11], [7, 2], [12, 10]],
        },
        'disruption': {
            'name': 'High disruption', 'description': 'Slippery main corridors, longer safe detours.',
            'width': 20, 'height': 13, 'start': [1, 1],
            'blocked': unique(high_shelves),
            'hazards': unique(rect(1, 6, 18, 6) + rect(7, 5, 9, 5) + rect(12, 7, 14, 7)),
            'tasks': [[18, 2], [18, 10], [2, 11], [8, 2], [12, 10]],
        },
        'narrow': {
            'name': 'Narrow aisles', 'description': 'Long shelves with limited cross-aisles.',
            'width': 20, 'height': 13, 'start': [1, 1],
            'blocked': unique(narrow_shelves),
            'hazards': unique(rect(4, 1, 6, 1) + rect(8, 11, 10, 11) + rect(12, 1, 14, 1)),
            'tasks': [[17, 3], [5, 10], [9, 3], [13, 10], [18, 11]],
        },
    }
