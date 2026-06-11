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


class TestLiftDistance:
    def test_default_when_section_missing(self):
        assert explode.lift_distance_mm({}) == (20.0, False)

    def test_default_when_config_none(self):
        assert explode.lift_distance_mm(None) == (20.0, False)

    def test_reads_configured_value(self):
        cfg = {'explode': {'distance_mm': 35}}
        assert explode.lift_distance_mm(cfg) == (35.0, False)

    def test_clamps_low(self):
        cfg = {'explode': {'distance_mm': 0}}
        assert explode.lift_distance_mm(cfg) == (1.0, True)

    def test_clamps_high(self):
        cfg = {'explode': {'distance_mm': 9000}}
        assert explode.lift_distance_mm(cfg) == (500.0, True)

    def test_non_numeric_falls_back_to_default(self):
        cfg = {'explode': {'distance_mm': 'banana'}}
        assert explode.lift_distance_mm(cfg) == (20.0, True)

    def test_mm_to_cm(self):
        assert explode.mm_to_cm(20) == 2.0


def face(axis, area, radius=0.15, center=(0, 0, 0)):
    return {'axis': axis, 'area': area, 'radius': radius, 'center': center}


class TestDominantAxis:
    def test_no_faces_returns_none(self):
        assert explode.dominant_axis([]) == (None, [])

    def test_single_face_wins(self):
        axis, coaxial = explode.dominant_axis([face((0, 0, 1), 2.0)])
        assert axis == pytest.approx((0, 0, 1))
        assert len(coaxial) == 1

    def test_largest_summed_area_wins(self):
        faces = [face((0, 0, 1), 1.0), face((0, 0, 1), 1.0),  # shank + head: 2.0 total
                 face((1, 0, 0), 1.5)]                          # cross-hole: 1.5
        axis, coaxial = explode.dominant_axis(faces)
        assert axis == pytest.approx((0, 0, 1))
        assert len(coaxial) == 2

    def test_antiparallel_axes_share_a_bucket(self):
        faces = [face((0, 0, 1), 1.0), face((0, 0, -1), 1.0),
                 face((1, 0, 0), 1.5)]
        axis, coaxial = explode.dominant_axis(faces)
        assert abs(axis[2]) == pytest.approx(1.0)
        assert len(coaxial) == 2

    def test_within_tolerance_buckets_together(self):
        tilted = explode.v_norm((math.sin(math.radians(0.5)), 0,
                                 math.cos(math.radians(0.5))))
        faces = [face((0, 0, 1), 1.0), face(tilted, 1.0), face((1, 0, 0), 1.5)]
        axis, _ = explode.dominant_axis(faces)
        assert axis == pytest.approx((0, 0, 1))

    def test_beyond_tolerance_buckets_apart(self):
        tilted = explode.v_norm((math.sin(math.radians(3.0)), 0,
                                 math.cos(math.radians(3.0))))
        faces = [face((0, 0, 1), 1.0), face(tilted, 1.0), face((1, 0, 0), 1.5)]
        axis, _ = explode.dominant_axis(faces)
        assert axis == pytest.approx((1, 0, 0))

    def test_unnormalized_input_axes_are_handled(self):
        axis, _ = explode.dominant_axis([face((0, 0, 7), 1.0)])
        assert axis == pytest.approx((0, 0, 1))


class TestHeadEndSign:
    def test_head_above_center_gives_positive(self):
        coaxial = [face((0, 0, 1), 1.0, radius=0.15, center=(0, 0, -0.5)),   # shank
                   face((0, 0, 1), 0.5, radius=0.275, center=(0, 0, 0.15))]  # head OD
        assert explode.head_end_sign(coaxial, (0, 0, 1), (0, 0, -0.35)) == 1

    def test_head_below_center_gives_negative(self):
        coaxial = [face((0, 0, 1), 1.0, radius=0.15, center=(0, 0, 0.5)),
                   face((0, 0, 1), 0.5, radius=0.275, center=(0, 0, -0.15))]
        assert explode.head_end_sign(coaxial, (0, 0, 1), (0, 0, 0.35)) == -1

    def test_equal_radii_is_inapplicable(self):
        coaxial = [face((0, 0, 1), 1.0, radius=0.125, center=(0, 0, 0))]  # nut bore
        assert explode.head_end_sign(coaxial, (0, 0, 1), (0, 0, 0)) is None

    def test_nearly_equal_radii_is_inapplicable(self):
        coaxial = [face((0, 0, 1), 1.0, radius=0.150, center=(0, 0, -0.5)),
                   face((0, 0, 1), 0.5, radius=0.154, center=(0, 0, 0.15))]
        assert explode.head_end_sign(coaxial, (0, 0, 1), (0, 0, -0.35)) is None

    def test_no_coaxial_faces_is_inapplicable(self):
        # the local-Z fallback path produces no coaxial faces
        assert explode.head_end_sign([], (0, 0, 1), (0, 0, 0)) is None


class TestChooseSign:
    def test_head_sign_used(self):
        assert explode.choose_sign(-1) == -1

    def test_fallback_is_positive(self):
        assert explode.choose_sign(None) == 1
