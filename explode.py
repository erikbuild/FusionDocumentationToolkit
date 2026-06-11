# ABOUTME: Explode/restore/flip of fastener occurrences for documentation
# ABOUTME: screenshots — pure decision logic plus Fusion API adapters.

import math

try:
    import adsk.core
    import adsk.fusion
except ImportError:
    adsk = None  # pure decision functions stay importable under pytest


# ---------------------------------------------------------------------------
# Pure decision logic — plain tuples in, plain values out. No adsk access.
# ---------------------------------------------------------------------------

def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_norm(a):
    length = math.sqrt(v_dot(a, a))
    return (a[0] / length, a[1] / length, a[2] / length)


DISTANCE_MM_DEFAULT = 20.0
DISTANCE_MM_MIN = 1.0
DISTANCE_MM_MAX = 500.0


def lift_distance_mm(config):
    """Lift distance from the config's explode section, clamped to the valid
    range. Returns (distance_mm, was_adjusted)."""
    raw = ((config or {}).get('explode') or {}).get('distance_mm', DISTANCE_MM_DEFAULT)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DISTANCE_MM_DEFAULT, True
    clamped = min(max(value, DISTANCE_MM_MIN), DISTANCE_MM_MAX)
    return clamped, clamped != value


def mm_to_cm(mm):
    return mm / 10.0


AXIS_BUCKET_TOLERANCE_DEG = 1.0


def dominant_axis(faces, tolerance_deg=AXIS_BUCKET_TOLERANCE_DEG):
    """The fastener's lift axis: bucket cylindrical/conical face axes by
    direction (antiparallel axes share a bucket) and return the direction with
    the largest summed face area, plus the faces in that bucket.

    The returned axis is unsigned — which way along it to lift is decided
    separately. Returns (None, []) when there are no faces.
    """
    cos_tol = math.cos(math.radians(tolerance_deg))
    buckets = []
    for f in faces:
        direction = v_norm(f['axis'])
        for bucket in buckets:
            if abs(v_dot(direction, bucket['direction'])) >= cos_tol:
                bucket['area'] += f['area']
                bucket['faces'].append(f)
                break
        else:
            buckets.append({'direction': direction, 'area': f['area'], 'faces': [f]})
    if not buckets:
        return None, []
    best = max(buckets, key=lambda b: b['area'])
    return best['direction'], best['faces']


HEAD_RADIUS_RATIO = 1.05  # head must be at least 5% larger than the shank


def head_end_sign(coaxial_faces, axis, body_center):
    """Sign along axis pointing toward the fastener's larger-diameter (head)
    end. 'Out' is always toward the head for seated screws, bolts, and flanged
    inserts. Returns None when inapplicable: no coaxial faces (local-Z
    fallback) or no distinct head (nuts, dowels, set screws)."""
    if not coaxial_faces:
        return None
    radii = [f['radius'] for f in coaxial_faces]
    if max(radii) < min(radii) * HEAD_RADIUS_RATIO:
        return None
    head_face = max(coaxial_faces, key=lambda f: f['radius'])
    position = v_dot(v_sub(head_face['center'], body_center), axis)
    if position == 0:
        return None
    return 1 if position > 0 else -1


def choose_sign(head_sign):
    """Final lift sign: toward the head end when the head-end heuristic decided
    one, else +axis (the user presses Flip if that guessed wrong). The v2
    ring-ray tie-breaker will slot in here as the middle case."""
    return head_sign if head_sign is not None else 1
