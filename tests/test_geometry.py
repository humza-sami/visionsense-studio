from frameinsight.geometry import (boxes_iou, point_in_polygon, segments_intersect,
                                   side_of_line)

SQUARE = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
# Concave "U" shape: notch cut into the top.
CONCAVE = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.6, 1.0), (0.6, 0.4),
           (0.4, 0.4), (0.4, 1.0), (0.0, 1.0)]


def test_point_in_square():
    assert point_in_polygon((0.5, 0.5), SQUARE)
    assert not point_in_polygon((0.1, 0.5), SQUARE)
    assert not point_in_polygon((0.5, 0.9), SQUARE)


def test_point_in_concave_polygon():
    assert point_in_polygon((0.2, 0.7), CONCAVE)     # left arm of the U
    assert point_in_polygon((0.8, 0.7), CONCAVE)     # right arm
    assert not point_in_polygon((0.5, 0.7), CONCAVE)  # inside the notch


def test_side_of_line():
    a, b = (0.0, 0.5), (1.0, 0.5)  # horizontal, pointing +x
    assert side_of_line(a, b, (0.5, 0.8)) == 1   # below (image coords) = left of travel
    assert side_of_line(a, b, (0.5, 0.2)) == -1  # above = right of travel
    assert side_of_line(a, b, (0.5, 0.5)) == 0


def test_segments_intersect():
    assert segments_intersect((0.5, 0.3), (0.5, 0.7), (0.1, 0.5), (0.9, 0.5))
    # Parallel, never touching
    assert not segments_intersect((0.0, 0.0), (1.0, 0.0), (0.0, 0.1), (1.0, 0.1))
    # Crossing the infinite line but beyond the segment's end
    assert not segments_intersect((0.95, 0.3), (0.95, 0.7), (0.1, 0.5), (0.9, 0.5))


def test_boxes_iou():
    assert boxes_iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1.0
    assert boxes_iou((0, 0, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5)) == 0.0
    v = boxes_iou((0, 0, 1, 1), (0.5, 0, 1, 1))
    assert abs(v - 1 / 3) < 1e-9
