"""Art touching a rectangle edge must not be admitted by corner-only checks."""

import numpy as np
import pytest

from services.worker.bubble_render import protected_text_rectangle


def test_white_corners_do_not_allow_art_crossing_middle_of_guard_ring():
    roi = np.full((160, 160, 3), 255, dtype=np.uint8)
    roi[78:82, 0:82] = 0
    # Every corner is white, but a line crosses every candidate left edge.
    with pytest.raises(ValueError, match="OPEN_BUBBLE_BOUNDARY"):
        protected_text_rectangle(roi, [40, 40, 120, 120], [10, 10, 150, 150], [0, 0, 160, 160])


def test_guard_ring_can_expand_around_near_edge_ink_without_touching_ring():
    roi = np.full((160, 160, 3), 255, dtype=np.uint8)
    roi[55:100, 38:45] = 0
    safe = protected_text_rectangle(roi, [40, 40, 120, 120], [10, 10, 150, 150], [0, 0, 160, 160])
    assert safe[60, 38] == 255
    assert not safe[0].any() and not safe[:, 0].any()
    assert safe[60, 35] == 0


def test_guard_ring_does_not_expand_outside_detected_bubble():
    roi = np.full((160, 160, 3), 255, dtype=np.uint8)
    with pytest.raises(ValueError, match="OPEN_BUBBLE_BOUNDARY"):
        protected_text_rectangle(roi, [40, 40, 120, 120], [38, 38, 122, 122], [0, 0, 160, 160])
