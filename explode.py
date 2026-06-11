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
