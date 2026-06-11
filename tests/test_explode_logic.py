# ABOUTME: Unit tests for the pure decision logic in explode.py — vector math,
# ABOUTME: axis inference, sign heuristics, and config parsing. No Fusion required.
import math

import pytest

import explode


class TestVectorHelpers:
    def test_dot(self):
        assert explode.v_dot((1, 2, 3), (4, 5, 6)) == 32

    def test_norm_produces_unit_vector(self):
        n = explode.v_norm((3, 0, 4))
        assert n == pytest.approx((0.6, 0, 0.8))

    def test_scale(self):
        assert explode.v_scale((1, -2, 0.5), 2) == (2, -4, 1.0)

    def test_sub(self):
        assert explode.v_sub((5, 5, 5), (1, 2, 3)) == (4, 3, 2)
