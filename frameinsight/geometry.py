"""Pure geometry on normalized [0,1] coordinates. No third-party deps."""

from __future__ import annotations

Point = tuple[float, float]


def point_in_polygon(pt: Point, polygon: list[Point]) -> bool:
    """Ray-casting point-in-polygon test. Works for concave polygons."""
    x, y = pt
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def side_of_line(a: Point, b: Point, p: Point) -> int:
    """Which side of the directed line a→b is p on?

    Returns +1 (left of travel direction), -1 (right), or 0 (on the line).
    For a horizontal gate line drawn left→right, "above" in image coords
    (smaller y) is -1 and "below" is +1.
    """
    cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    if cross > 1e-12:
        return 1
    if cross < -1e-12:
        return -1
    return 0


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    """Do segments p1–p2 and q1–q2 intersect (including endpoints)?"""

    def orient(a: Point, b: Point, c: Point) -> int:
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    def on_seg(a: Point, b: Point, c: Point) -> bool:
        return (min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= c[1] <= max(a[1], b[1]))

    o1, o2 = orient(p1, p2, q1), orient(p1, p2, q2)
    o3, o4 = orient(q1, q2, p1), orient(q1, q2, p2)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and on_seg(p1, p2, q1):
        return True
    if o2 == 0 and on_seg(p1, p2, q2):
        return True
    if o3 == 0 and on_seg(q1, q2, p1):
        return True
    if o4 == 0 and on_seg(q1, q2, p2):
        return True
    return False


def boxes_iou(a: tuple[float, float, float, float],
              b: tuple[float, float, float, float]) -> float:
    """IoU of two (x, y, w, h) boxes."""
    ax1, ay1, ax2, ay2 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx1, by1, bx2, by2 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = ix * iy
    if inter <= 0.0:
        return 0.0
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0
