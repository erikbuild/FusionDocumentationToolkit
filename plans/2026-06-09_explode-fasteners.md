# Explode Fasteners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three new silent commands (Explode Fasteners / Restore Fasteners / Flip Last Explode) that copy selected fastener occurrences 15–20mm out along their inferred insertion axis, hide the originals for empty-hole documentation screenshots, and cleanly restore everything afterward.

**Architecture:** A new `explode.py` module beside the main add-in file holds all feature logic, split into pure decision functions (plain-tuple data, pytest-testable, no `adsk` imports needed) and Fusion adapter functions (verified by a self-contained in-Fusion integration script). The main file only registers the three commands and delegates. Spec: `specs/2026-06-09_explode-fasteners.md`. API research: `research/2026-06-09_fastener-move-copy-feasibility.md`.

**Tech Stack:** Fusion 360 add-in API (Python, `adsk.core`/`adsk.fusion`), pytest for pure logic, in-Fusion script for integration/E2E.

---

## Ground Rules For The Executing Agent

1. **NEVER run `git commit`.** Erik commits all changes himself. Every "Checkpoint" step means: stop, summarize what changed, suggest a commit message, and wait for Erik.
2. **You cannot run Fusion.** Steps marked **[FUSION — Erik runs]** require Erik to execute a script inside Fusion and paste the Text Commands palette output back. Stop and wait at each one.
3. **Spike findings gate later tasks.** Task 2's findings are recorded in this file. If a finding contradicts the assumed API behavior in Tasks 6–12 (Finding 5 gates the head-end heuristic in Task 6; Findings 1/3/4 gate the adapters in Tasks 8–10), STOP and revise with Erik before proceeding — do not improvise around a failed assumption.
4. All distances inside the API are **centimeters**. Config values are millimeters. Conversion happens only at `lift_distance_mm` → `mm_to_cm`.
5. Fusion's Python is 3.x but has no pip packages; `explode.py` must import cleanly both inside Fusion (adsk available) and under pytest (adsk absent) — that's what the guarded import in Task 3 is for.
6. **Test runner is `uv run pytest`.** The machine's Python is Homebrew's (externally-managed, PEP 668), so pytest lives in a project `.venv` created with `uv venv` + `uv pip install pytest`. Wherever a later task shows `python3 -m pytest ...`, run it as `uv run pytest ...`. `.venv/` is gitignored.

---

### Task 1: Branch and test scaffolding

**Files:**
- Create: `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create the working branch**

```bash
git -C /Users/erik/Code/FusionDocumentationToolkit checkout -b explode-fasteners
```

Expected: `Switched to a new branch 'explode-fasteners'`

- [ ] **Step 2: Verify pytest is available**

```bash
python3 -m pytest --version
```

Expected: a version line (e.g. `pytest 8.x`). If the command fails, run `python3 -m pip install --user pytest` and re-verify.

- [ ] **Step 3: Create `tests/conftest.py`** so tests can `import explode` from the repo root:

```python
# ABOUTME: Pytest configuration — puts the repo root on sys.path so tests
# ABOUTME: can import the explode module without packaging.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 4: Check `.gitignore` covers `__pycache__`**

Read `.gitignore`. If it does not already ignore `__pycache__/`, append a line containing exactly `__pycache__/`.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add test scaffolding for explode feature.`

---

### Task 2: Pre-implementation spike (verifies five undocumented API behaviors)

**Files:**
- Create: `tests/fusion_spike/ExplodeSpike.py`
- Create: `tests/fusion_spike/ExplodeSpike.manifest`

The spec flags five behaviors that must be verified in Fusion before the adapter code is final: (1) `addExistingComponent` transform coordinate space with a nested original, (2) `deleteMe` timeline cleanliness in parametric mode, (3) deepest-occurrence resolution from a body proxy via `allOccurrencesByComponent` + entity-token matching, (4) attribute round-trip on occurrences via `findAttributes` (Restore/Flip depend on it), (5) head-end geometry from proxy faces — world-space readback and whether the head face's surface origin distinguishes the head end (the sole v1 sign source now that ring-ray is deferred to v2).

- [ ] **Step 1: Write the spike script** at `tests/fusion_spike/ExplodeSpike.py`:

```python
# ABOUTME: One-shot Fusion script that verifies three API behaviors the
# ABOUTME: explode feature depends on. Logs findings to the Text Commands palette.
import adsk.core
import adsk.fusion
import traceback


def log(app, msg):
    app.log('[ExplodeSpike] ' + msg)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Fixture: a subassembly containing one child component with a small box body,
        # the subassembly itself translated away from origin so coordinate spaces differ.
        sub_transform = adsk.core.Matrix3D.create()
        sub_transform.translation = adsk.core.Vector3D.create(10.0, 0, 0)
        sub_occ = root.occurrences.addNewComponent(sub_transform)
        sub_occ.component.name = 'SubAssembly'

        inner_transform = adsk.core.Matrix3D.create()
        inner_transform.translation = adsk.core.Vector3D.create(0, 5.0, 0)
        inner_occ = sub_occ.component.occurrences.addNewComponent(inner_transform)
        inner_occ.component.name = 'InnerPart'

        sketch = inner_occ.component.sketches.add(inner_occ.component.xYConstructionPlane)
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(1, 1, 0))
        extrudes = inner_occ.component.features.extrudeFeatures
        extrudes.addSimple(sketch.profiles.item(0),
                           adsk.core.ValueInput.createByReal(1.0),
                           adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        # --- Finding 1: addExistingComponent transform coordinate space ---
        # The nested InnerPart's world translation is (10, 5, 0). Add a copy to root
        # with translation (10, 5, 3): if the matrix is root-relative, the copy's
        # transform2.translation reads back as exactly (10, 5, 3).
        copy_t = adsk.core.Matrix3D.create()
        copy_t.translation = adsk.core.Vector3D.create(10.0, 5.0, 3.0)
        timeline_before_copy = design.timeline.count
        copy_occ = root.occurrences.addExistingComponent(inner_occ.component, copy_t)
        rt = copy_occ.transform2.translation
        log(app, 'FINDING 1 (addExistingComponent space): requested (10,5,3), '
                 'transform2.translation reads ({:.3f},{:.3f},{:.3f}) -> {}'.format(
                     rt.x, rt.y, rt.z,
                     'ROOT-RELATIVE as assumed' if (abs(rt.x - 10) < 1e-6 and abs(rt.y - 5) < 1e-6 and abs(rt.z - 3) < 1e-6)
                     else 'NOT root-relative — STOP AND REVISE PLAN'))

        # --- Finding 2: deleteMe timeline cleanliness (parametric mode) ---
        timeline_after_copy = design.timeline.count
        ok = copy_occ.deleteMe()
        timeline_after_delete = design.timeline.count
        log(app, 'FINDING 2 (deleteMe timeline): count before copy={}, after copy={}, '
                 'after delete={} -> {}'.format(
                     timeline_before_copy, timeline_after_copy, timeline_after_delete,
                     'CLEAN (back to pre-copy count)' if timeline_after_delete == timeline_before_copy
                     else 'LEAVES TIMELINE RESIDUE — note for Restore design'))
        log(app, 'FINDING 2b: deleteMe returned {}'.format(ok))

        # --- Finding 3: deepest-occurrence resolution from a body proxy ---
        # Take the nested body as a root-context proxy (the same thing a canvas
        # pick yields), then resolve it back to the deepest occurrence.
        nested_proxy = None
        for i in range(root.allOccurrences.count):
            occ = root.allOccurrences.item(i)
            if occ.component.name == 'InnerPart':
                nested_proxy = occ
        body_proxy = nested_proxy.bRepBodies.item(0)
        log(app, 'FINDING 3a: body proxy assemblyContext fullPathName = {!r}'.format(
            body_proxy.assemblyContext.fullPathName if body_proxy.assemblyContext else None))
        native = body_proxy.nativeObject if body_proxy.assemblyContext else body_proxy
        comp = native.parentComponent
        candidates = root.allOccurrencesByComponent(comp)
        log(app, 'FINDING 3b: native parentComponent = {!r}, candidate occurrences = {}'.format(
            comp.name, candidates.count))
        matched = None
        for i in range(candidates.count):
            cand = candidates.item(i)
            for j in range(cand.bRepBodies.count):
                if cand.bRepBodies.item(j).entityToken == body_proxy.entityToken:
                    matched = cand
        log(app, 'FINDING 3c: token match resolved to {!r} -> {}'.format(
            matched.fullPathName if matched else None,
            'RESOLUTION WORKS' if matched and matched.fullPathName == nested_proxy.fullPathName
            else 'RESOLUTION FAILED — STOP AND REVISE PLAN'))

        # --- Finding 4: attribute round-trip on occurrences (foundation of Restore/Flip) ---
        # Tag an occurrence (not a component) and confirm design.findAttributes
        # returns it, parent casts back to Occurrence, and a token value round-trips.
        GROUP = 'FusionDocumentationToolkit'
        inner_occ.attributes.add(GROUP, 'spikeOriginal', '1')
        sub_occ.attributes.add(GROUP, 'spikeCopy', inner_occ.entityToken)
        found_orig = design.findAttributes(GROUP, 'spikeOriginal')
        found_copy = design.findAttributes(GROUP, 'spikeCopy')
        n_orig = len(found_orig) if found_orig else 0
        n_copy = len(found_copy) if found_copy else 0
        parent_ok = bool(n_copy and adsk.fusion.Occurrence.cast(found_copy[0].parent))
        value_ok = bool(n_copy and found_copy[0].value == inner_occ.entityToken)
        log(app, 'FINDING 4 (occurrence attributes): findAttributes -> {} original, {} copy; '
                 'parent casts to Occurrence={}, value round-trips={} -> {}'.format(
                     n_orig, n_copy, parent_ok, value_ok,
                     'ATTRIBUTES WORK' if (n_orig and n_copy and parent_ok and value_ok)
                     else 'ATTRIBUTES BROKEN — STOP AND REVISE PLAN'))

        # --- Finding 5: head-end geometry from proxy faces (the sole v1 sign source) ---
        # A screw (shank r0.15 along -Z, head r0.275 on top) nested in a subassembly
        # translated to world z=20. Confirm proxy face geometry is world-space and the
        # head face's origin projects measurably farther along the axis than the shank's.
        screw_sub_t = adsk.core.Matrix3D.create()
        screw_sub_t.translation = adsk.core.Vector3D.create(0, 0, 20.0)
        screw_sub = root.occurrences.addNewComponent(screw_sub_t)
        screw_sub.component.name = 'ScrewSub'
        screw_occ = screw_sub.component.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        sc = screw_occ.component
        sc.name = 'SpikeScrew'
        sc_ex = sc.features.extrudeFeatures
        shank_sk = sc.sketches.add(sc.xYConstructionPlane)
        shank_sk.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), 0.15)
        shank_in = sc_ex.createInput(shank_sk.profiles.item(0),
                                     adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        shank_in.setDistanceExtent(False, adsk.core.ValueInput.createByReal(-1.0))
        sc_ex.add(shank_in)
        head_sk = sc.sketches.add(sc.xYConstructionPlane)
        head_sk.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(0, 0, 0), 0.275)
        head_in = sc_ex.createInput(head_sk.profiles.item(0),
                                    adsk.fusion.FeatureOperations.JoinFeatureOperation)
        head_in.setDistanceExtent(False, adsk.core.ValueInput.createByReal(0.3))
        sc_ex.add(head_in)
        screw_proxy = None
        for i in range(root.allOccurrences.count):
            o = root.allOccurrences.item(i)
            if o.component.name == 'SpikeScrew':
                screw_proxy = o
        cyls = []  # (radius, origin_tuple, axis_tuple)
        for bi in range(screw_proxy.bRepBodies.count):
            b = screw_proxy.bRepBodies.item(bi)
            for fi in range(b.faces.count):
                g = b.faces.item(fi).geometry
                if g.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                    cyls.append((g.radius, (g.origin.x, g.origin.y, g.origin.z),
                                 (g.axis.x, g.axis.y, g.axis.z)))
        for r, o, a in cyls:
            log(app, 'FINDING 5a: cyl r={:.3f} origin=({:.3f},{:.3f},{:.3f}) axis=({:.3f},{:.3f},{:.3f})'.format(
                r, o[0], o[1], o[2], a[0], a[1], a[2]))
        world_space = bool(cyls) and all(o[2] > 15.0 for _, o, _a in cyls)
        log(app, 'FINDING 5b: proxy geometry world-space (origins near z~20, not z~0) -> {}'.format(
            'WORLD-SPACE as assumed' if world_space else 'NOT world-space — REVISE axis_faces/body_center'))
        if len(cyls) >= 2:
            by_r = sorted(cyls, key=lambda c: c[0])
            shank_o, head = by_r[0][1], by_r[-1]
            head_o, axis = head[1], head[2]
            proj = ((head_o[0] - shank_o[0]) * axis[0] + (head_o[1] - shank_o[1]) * axis[1]
                    + (head_o[2] - shank_o[2]) * axis[2])
            log(app, 'FINDING 5c: head origin projects {:.4f} beyond shank along axis -> {}'.format(
                proj, 'HEAD-END DISTINGUISHABLE' if abs(proj) > 1e-4
                else 'ORIGINS COINCIDE — head_end_sign UNRELIABLE, use face bbox instead'))
        else:
            log(app, 'FINDING 5c: expected >=2 cylindrical faces, got {} — STOP AND REVISE'.format(len(cyls)))

        doc.close(False)
        log(app, 'Spike complete. Paste all [ExplodeSpike] lines back to the agent.')
    except Exception:
        if ui:
            ui.messageBox('Spike failed:\n{}'.format(traceback.format_exc()))
```

- [ ] **Step 2: Write the manifest** at `tests/fusion_spike/ExplodeSpike.manifest`:

```json
{
    "autodeskProduct": "Fusion360",
    "type": "script",
    "scriptType": "python",
    "description": "Verifies API behaviors for the explode-fasteners feature."
}
```

- [ ] **Step 3 [FUSION — Erik runs]: Run the spike.** In Fusion: Utilities → Add-Ins → Scripts tab → green “+” → select `tests/fusion_spike/`, run **ExplodeSpike**, then copy every `[ExplodeSpike]` line from the Text Commands palette back into the conversation.

- [ ] **Step 4: Record findings in this plan file.** Edit this checklist item to include the five findings verbatim. STOP and revise with Erik before continuing if any of these fail:
  - Finding 1 not root-relative → revise Tasks 9/10 (the lift transform).
  - Finding 3 fails → revise Task 8 (selection resolution).
  - Finding 4 shows attributes broken → STOP; the entire tracking design must change before Task 10.
  - Finding 5b not world-space, or 5c shows origins coincide → revise Task 6's `head_end_sign` to take an axial reference from the face bounding box instead of the surface origin (and Task 9's `axis_faces` to supply it) before writing those tests.
  - Finding 2 leaves timeline residue → not a blocker: note it here and in the spec's Parametric vs Direct Mode section, surface it to Erik, and adjust the Task 12 timeline assertion to expect the residue (Restore still works; the timeline just isn't pristine).

**Spike findings (recorded 2026-06-11):**
- **Finding 1 — PASS.** `addExistingComponent` on `root.occurrences` is ROOT-RELATIVE: requested (10,5,3), `transform2.translation` read back (10,5,3). Tasks 9/10 lift transform is sound.
- **Finding 2 — PASS (clean).** Timeline count 4→5 (copy)→4 (deleteMe); `deleteMe` returned True. No residue, so `EXPECTED_TIMELINE_RESIDUE = 0` in Task 12.
- **Finding 3 — PASS.** Body proxy `assemblyContext = 'SubAssembly:1+InnerPart:1'`; `nativeObject.parentComponent` + `allOccurrencesByComponent` + entity-token match resolved back to `SubAssembly:1+InnerPart:1`. Task 8 selection resolution is sound.
- **Finding 4 — PASS.** `findAttributes` returned the tagged original and copy; `attr.parent` cast to Occurrence; the stored token round-tripped and `findEntityByToken` resolved it back to the original occurrence. Restore/Flip tracking is sound. **Constraint learned:** `entityToken` is only valid for proxies whose top-level parent is the root component (the v1 spike crashed reading it from a *native* nested occurrence). The design only ever tags root-context occurrences (selections + `addExistingComponent` copies), so it's safe — but Task 8/10 should keep that invariant.
- **Finding 5 — 5a/5b PASS, 5c FAIL → head_end_sign revised.** 5b: proxy face geometry is world-space (origins at z≈20). 5a/5c: both the head (r0.275) and shank (r0.15) cylinder faces report `origin=(0,0,20)` — the **surface origin is at the sketch plane, not the face's physical location**, so it can't reliably mark the head end (works on a benign fixture by luck, fails when the part's sketch plane is placed differently). **Resolution (plan-pre-authorized): `axis_faces` supplies each face's `boundingBox` center as its axial position; `head_end_sign` uses that instead of the surface origin.** Finding 5d (added to the spike) confirms the bbox approach before Task 6 is written.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add API spike script for explode feature.`

---

### Task 3: Pure vector helpers

**Files:**
- Create: `explode.py`
- Create: `tests/test_explode_logic.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_explode_logic.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'explode'`.

- [ ] **Step 3: Create `explode.py` with the guarded import and vector helpers:**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add explode module with vector helpers.`

---

### Task 4: Config parsing (distance clamp and unit conversion)

**Files:**
- Modify: `explode.py`
- Modify: `tests/test_explode_logic.py`

- [ ] **Step 1: Append the failing tests** to `tests/test_explode_logic.py`:

```python
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
```

- [ ] **Step 2: Run to verify the new tests fail**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: 4 passed (Task 3), 7 failed with `AttributeError: module 'explode' has no attribute 'lift_distance_mm'`.

- [ ] **Step 3: Append the implementation** to the pure-logic section of `explode.py`:

```python
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
```

- [ ] **Step 4: Run to verify all pass**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add lift distance config parsing.`

---

### Task 5: Axis inference (bucketing cylindrical-face axes)

**Files:**
- Modify: `explode.py`
- Modify: `tests/test_explode_logic.py`

Face records are plain dicts: `{'axis': (x,y,z), 'area': float, 'radius': float, 'center': (x,y,z)}` — the adapter (Task 9) builds them from world-space face proxies. `center` is each face's bounding-box center (its physical axial position); spike Finding 5c showed the cylinder *surface* origin sits at the modeling sketch plane and can't mark the head end.

- [ ] **Step 1: Append the failing tests:**

```python
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
```

- [ ] **Step 2: Run to verify the new tests fail**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -k Dominant -v
```

Expected: 7 failed with `AttributeError: module 'explode' has no attribute 'dominant_axis'`.

- [ ] **Step 3: Append the implementation:**

```python
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
```

- [ ] **Step 4: Run the full suite**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: 18 passed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add dominant axis inference.`

---

### Task 6: Sign heuristics (head end and final choice)

**Files:**
- Modify: `explode.py`
- Modify: `tests/test_explode_logic.py`

- [ ] **Step 1: Append the failing tests:**

```python
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
```

- [ ] **Step 2: Run to verify the new tests fail**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -k "HeadEnd or ChooseSign" -v
```

Expected: 7 failed with `AttributeError`.

- [ ] **Step 3: Append the implementation:**

```python
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
```

- [ ] **Step 4: Run the full suite**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/test_explode_logic.py -v
```

Expected: 25 passed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add lift sign heuristics.`

---

### Task 7: Ring-ray sign tie-breaker — DEFERRED TO v2 (skip)

The offset ring-ray test is out of scope for v1. v1 picks the lift sign from the
head-end heuristic (Task 6) and falls back to +axis, so headless fasteners (nuts,
dowels, set screws) may guess wrong and need one **Flip Last Explode**. There is
no code to write here.

The v2 work this task will cover when revived: the pure helpers `ring_radius` /
`ray_threshold` / `ring_origins` / `ring_ray_sign` (plus the `v_cross` /
`perpendicular_basis` vector helpers they need), the `cast_side_rays` adapter, the
`axial_half_extent` / `radial_extent` outputs of `body_metrics`, and wiring the
ray sign into `choose_sign` as its middle case. See the spec's Out of Scope
section for the design sketch.

**No checkpoint — nothing changes in this task.**

---

### Task 8: Fusion adapters — module state, logging, selection resolution

**Files:**
- Modify: `explode.py`

Adapter code can't run under pytest (no `adsk`); it is exercised by the integration script (Task 12) and validated by the spike findings (Task 2). Append everything below to `explode.py` under a clearly separated section.

- [ ] **Step 1: Append module state, constants, and logging:**

```python
# ---------------------------------------------------------------------------
# Fusion adapters — everything below touches adsk and runs only inside Fusion.
# ---------------------------------------------------------------------------

ATTR_GROUP = 'FusionDocumentationToolkit'
ATTR_COPY = 'explodedCopy'
ATTR_ORIGINAL = 'explodedOriginal'
LOG_PREFIX = '[ExplodeFasteners] '

EXPLODE_CMD_ID = 'ExplodeFastenersCmd'
EXPLODE_CMD_NAME = 'Explode Fasteners'
EXPLODE_CMD_DESCRIPTION = ('Copy the selected fasteners out along their insertion axes '
                           'and hide the originals, for empty-hole documentation shots.')
RESTORE_CMD_ID = 'RestoreFastenersCmd'
RESTORE_CMD_NAME = 'Restore Fasteners'
RESTORE_CMD_DESCRIPTION = 'Delete all exploded fastener copies and unhide the originals.'
FLIP_CMD_ID = 'FlipLastExplodeCmd'
FLIP_CMD_NAME = 'Flip Last Explode'
FLIP_CMD_DESCRIPTION = 'Re-lift the most recent explode batch in the opposite direction.'

_app = None
_ui = None
_config = None
_handlers = []
_pending_selection = []
_last_batch = None  # {'doc_token': str, 'items': [{'token','axis','sign','distance_cm'}]}


def init(app, ui, config):
    """Wire the module to the running add-in. Called from run()."""
    global _app, _ui, _config, _pending_selection, _last_batch
    _app = app
    _ui = ui
    _config = config
    _pending_selection = []
    _last_batch = None


def log(message):
    if _app:
        try:
            _app.log(LOG_PREFIX + message)
        except Exception:
            pass


def active_design():
    return adsk.fusion.Design.cast(_app.activeProduct)


def occurrence_label(occ):
    try:
        return occ.fullPathName
    except Exception:
        return '(unnamed occurrence)'
```

- [ ] **Step 2: Append tag inspection and selection resolution** (mechanism validated by spike Finding 3):

```python
def has_tag(occ, attr_name):
    try:
        return occ.attributes.itemByName(ATTR_GROUP, attr_name) is not None
    except Exception:
        return False


def resolve_to_occurrences(entities, root):
    """Map raw selection entities (occurrences, or face/body proxies from
    canvas picks) to the deepest occurrences owning them, deduped and with
    already-exploded items filtered out. Returns (occurrences, skipped) where
    skipped is a list of (label, reason) for palette logging."""
    occurrences = []
    skipped = []
    seen_tokens = set()
    for ent in entities:
        occ = adsk.fusion.Occurrence.cast(ent)
        if not occ:
            body = None
            face = adsk.fusion.BRepFace.cast(ent)
            if face:
                body = face.body
            else:
                body = adsk.fusion.BRepBody.cast(ent)
            if not body:
                skipped.append((str(ent.objectType), 'not an occurrence or body pick'))
                continue
            native = body.nativeObject if body.assemblyContext else body
            comp = native.parentComponent
            if comp == root:
                skipped.append((body.name, 'root-component geometry, no occurrence'))
                continue
            candidates = root.allOccurrencesByComponent(comp)
            occ = None
            for i in range(candidates.count):
                cand = candidates.item(i)
                for j in range(cand.bRepBodies.count):
                    if cand.bRepBodies.item(j).entityToken == body.entityToken:
                        occ = cand
                        break
                if occ:
                    break
            if not occ:
                skipped.append((body.name, 'could not resolve owning occurrence'))
                continue
        if occ.entityToken in seen_tokens:
            continue
        if has_tag(occ, ATTR_COPY):
            skipped.append((occurrence_label(occ), 'is an exploded copy'))
            continue
        if has_tag(occ, ATTR_ORIGINAL):
            skipped.append((occurrence_label(occ), 'already exploded'))
            continue
        seen_tokens.add(occ.entityToken)
        occurrences.append(occ)
    return occurrences, skipped
```

- [ ] **Step 3: Sanity-check the file still imports cleanly without Fusion**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -c "import explode; print('import ok')" && python3 -m pytest tests/test_explode_logic.py -q
```

Expected: `import ok`, 25 passed.

- [ ] **Step 4: Checkpoint — ask Erik to review and commit.** Suggested message: `Add explode module state and selection resolution.`

---

### Task 9: Fusion adapters — geometry extraction and inference

**Files:**
- Modify: `explode.py`

Note: the cone branch of `axis_faces` reads `geom.radius`. Confirm `adsk.core.Cone` exposes `radius` in this Fusion build (countersunk/chamfer faces hit that branch); a missing property is a runtime `AttributeError` pytest can't catch. If it's absent, drop the cone branch for v1 — cylinders alone cover the fixture's fasteners.

- [ ] **Step 1: Append face extraction and the body center:**

```python
def axis_faces(occ):
    """Face records for the pure inference functions, from the occurrence's
    bodies in world space (proxies). Cylinders and cones only. 'center' is the
    face's bounding-box center — its physical axial position. (The surface
    origin sits at the modeling sketch plane, not the face, so it can't mark
    the head end — spike Finding 5c.)"""
    records = []
    for i in range(occ.bRepBodies.count):
        body = occ.bRepBodies.item(i)
        for j in range(body.faces.count):
            f = body.faces.item(j)
            geom = f.geometry
            if geom.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                axis, radius = geom.axis, geom.radius
            elif geom.surfaceType == adsk.core.SurfaceTypes.ConeSurfaceType:
                axis, radius = geom.axis, geom.radius
            else:
                continue
            bb = f.boundingBox
            center = ((bb.minPoint.x + bb.maxPoint.x) / 2.0,
                      (bb.minPoint.y + bb.maxPoint.y) / 2.0,
                      (bb.minPoint.z + bb.maxPoint.z) / 2.0)
            records.append({'axis': (axis.x, axis.y, axis.z),
                            'area': f.area,
                            'radius': radius,
                            'center': center})
    return records


def body_center(occ):
    """Centroid of the occurrence's combined body bounding-box corners, in
    world space — the reference point the head-end heuristic measures from."""
    corners = []
    for i in range(occ.bRepBodies.count):
        bb = occ.bRepBodies.item(i).boundingBox
        lo, hi = bb.minPoint, bb.maxPoint
        for x in (lo.x, hi.x):
            for y in (lo.y, hi.y):
                for z in (lo.z, hi.z):
                    corners.append((x, y, z))
    return (sum(c[0] for c in corners) / len(corners),
            sum(c[1] for c in corners) / len(corners),
            sum(c[2] for c in corners) / len(corners))
```

- [ ] **Step 2: Append the per-fastener inference:**

```python
def infer_lift_vector(occ):
    """The Phase-A decision for one occurrence: (axis, sign) or (None, reason)
    when no axis can be inferred. Reads only the occurrence's own geometry —
    nothing about the surrounding scene — so it is order-independent."""
    faces = axis_faces(occ)
    axis, coaxial = dominant_axis(faces)
    if axis is None:
        m = occ.transform2
        z = (m.getCell(0, 2), m.getCell(1, 2), m.getCell(2, 2))
        if v_dot(z, z) == 0:
            return None, 'no cylindrical faces and degenerate transform'
        axis = v_norm(z)
        coaxial = []
    sign = choose_sign(head_end_sign(coaxial, axis, body_center(occ)))
    return (axis, sign), None
```

- [ ] **Step 3: Sanity-check imports and tests**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -c "import explode; print('import ok')" && python3 -m pytest tests/test_explode_logic.py -q
```

Expected: `import ok`, 25 passed.

- [ ] **Step 4: Checkpoint — ask Erik to review and commit.** Suggested message: `Add geometry extraction and inference adapters.`

---

### Task 10: Explode, restore, and flip engines

**Files:**
- Modify: `explode.py`

- [ ] **Step 1: Append the explode engine** (two-phase per the spec — all inference before any mutation):

```python
def timeline_at_end(design):
    """False only in parametric mode with the marker rolled back — API
    operations would land mid-history."""
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        return True
    timeline = design.timeline
    return timeline.markerPosition == timeline.count


def lifted_transform(occ, axis, sign, distance_cm):
    """Root-space creation transform for the copy: the original's world
    transform translated by sign * axis * distance."""
    m = occ.transform2.copy()
    t = m.translation
    offset = v_scale(axis, sign * distance_cm)
    t.x += offset[0]
    t.y += offset[1]
    t.z += offset[2]
    m.translation = t
    return m


def create_lifted_copy(design, occ, axis, sign, distance_cm):
    """Phase-B mutation for one fastener: copy into root at the lifted
    position, tag both occurrences, show the copy, hide the original. Returns
    the copy or None on failure."""
    root = design.rootComponent
    copy_occ = root.occurrences.addExistingComponent(
        occ.component, lifted_transform(occ, axis, sign, distance_cm))
    if not copy_occ:
        return None
    copy_occ.attributes.add(ATTR_GROUP, ATTR_COPY, occ.entityToken)
    occ.attributes.add(ATTR_GROUP, ATTR_ORIGINAL, '1')
    # Force the copy visible: a new occurrence inherits its source's light-bulb
    # state, and during Flip the source original is already hidden.
    copy_occ.isLightBulbOn = True
    occ.isLightBulbOn = False
    return copy_occ


def explode_occurrences(occurrences, distance_cm, design):
    """Explode a batch: infer axis+sign for every occurrence against the
    untouched scene (Phase A), then create copies, tag, and hide (Phase B).
    Returns (exploded_count, skipped) where skipped is [(label, reason)]."""
    global _last_batch
    root = design.rootComponent
    plans = []
    skipped = []
    for occ in occurrences:
        result, reason = infer_lift_vector(occ)
        if result is None:
            skipped.append((occurrence_label(occ), reason))
            continue
        axis, sign = result
        plans.append({'occ': occ, 'axis': axis, 'sign': sign})
    if not plans:
        return 0, skipped

    items = []
    for plan in plans:
        copy_occ = create_lifted_copy(design, plan['occ'], plan['axis'],
                                      plan['sign'], distance_cm)
        if not copy_occ:
            skipped.append((occurrence_label(plan['occ']), 'copy creation failed'))
            continue
        items.append({'token': plan['occ'].entityToken,
                      'axis': plan['axis'],
                      'sign': plan['sign'],
                      'distance_cm': distance_cm})
    if items:
        _last_batch = {'doc_token': root.entityToken, 'items': items}
    return len(items), skipped
```

- [ ] **Step 2: Append the restore engine:**

```python
def find_tagged_attributes(design, attr_name):
    """All attributes with this name in our group, as a plain list so callers
    can delete attributes or their owning entities while iterating without
    skipping items."""
    attrs = design.findAttributes(ATTR_GROUP, attr_name)
    return list(attrs) if attrs else []


def resolve_token(design, token):
    entities = design.findEntityByToken(token)
    if entities and len(entities) > 0:
        return adsk.fusion.Occurrence.cast(entities[0])
    return None


def delete_copy(copy_occ):
    """Delete an exploded copy and its tag together. Deleting the occurrence
    alone leaves the explodedCopy attribute behind in the design's attribute
    store, so the tag must be removed explicitly."""
    tag = copy_occ.attributes.itemByName(ATTR_GROUP, ATTR_COPY)
    if tag:
        tag.deleteMe()
    copy_occ.deleteMe()


def restore_all(design):
    """Delete every tagged copy and unhide every tagged original, across all
    outstanding batches from any session. Returns the restored copy count."""
    global _last_batch
    restored = 0
    for attr in find_tagged_attributes(design, ATTR_COPY):
        copy_occ = adsk.fusion.Occurrence.cast(attr.parent) if attr.parent else None
        original = resolve_token(design, attr.value)
        if original:
            original.isLightBulbOn = True
        else:
            log('Restore: original for one copy no longer exists; deleting copy anyway')
        if copy_occ:
            delete_copy(copy_occ)
            restored += 1
        else:
            attr.deleteMe()  # orphaned tag (copy already gone)
    for attr in find_tagged_attributes(design, ATTR_ORIGINAL):
        original = adsk.fusion.Occurrence.cast(attr.parent) if attr.parent else None
        if original:
            original.isLightBulbOn = True
        attr.deleteMe()
    _last_batch = None
    return restored
```

- [ ] **Step 3: Append the flip engine** (delete-and-re-explode with negated sign, per the spec — never a transform edit):

```python
def flip_last_batch(design):
    """Mirror the most recent batch to the other side of its parts. Returns
    (flipped_count, reason) — reason is set when nothing could be flipped."""
    global _last_batch
    root = design.rootComponent
    if not _last_batch:
        return 0, 'no explode batch this session'
    if _last_batch['doc_token'] != root.entityToken:
        return 0, 'last explode batch belongs to a different document'

    copies_by_original = {}
    for attr in find_tagged_attributes(design, ATTR_COPY):
        if attr.parent:
            copies_by_original[attr.value] = adsk.fusion.Occurrence.cast(attr.parent)

    surviving = []
    flipped = 0
    for item in _last_batch['items']:
        original = resolve_token(design, item['token'])
        if not original:
            log('Flip: original no longer resolves; dropping batch entry')
            continue
        old_copy = copies_by_original.get(item['token'])
        if old_copy:
            delete_copy(old_copy)
        else:
            log('Flip: copy for {} was missing; recreating'.format(occurrence_label(original)))
        item['sign'] = -item['sign']
        new_copy = create_lifted_copy(design, original, item['axis'],
                                      item['sign'], item['distance_cm'])
        if new_copy:
            flipped += 1
            surviving.append(item)
    _last_batch['items'] = surviving
    if not surviving:
        _last_batch = None
    return flipped, None
```

Note: `create_lifted_copy` re-tags the original (`attributes.add` overwrites the same-named attribute) and re-asserts `isLightBulbOn = False`, which covers the spec's flip-after-stray-undo case.

- [ ] **Step 4: Sanity-check imports and tests**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -c "import explode; print('import ok')" && python3 -m pytest tests/test_explode_logic.py -q
```

Expected: `import ok`, 25 passed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add explode, restore, and flip engines.`

---

### Task 11: Command handlers and main-file registration

**Files:**
- Modify: `explode.py`
- Modify: `erikbuild-FusionDocumentationToolkit.py:4-11` (imports), `:409-454` (run), `:457-479` (stop)
- Modify: `config.json`
- Create: `resources/explodeFasteners/`, `resources/restoreFasteners/`, `resources/flipExplode/` (placeholder icons)

- [ ] **Step 1: Append the command handlers** to `explode.py`:

```python
class ExplodeCreatedHandler(_CommandCreatedHandler):
    """Captures the user's pre-selection before Fusion clears it, then defers
    all work to execute. isAutoExecute keeps the command dialog-free so a
    hotkey press fires instantly (mirrors the Capture Image pattern)."""

    def notify(self, args):
        global _pending_selection
        try:
            cmd = args.command
            try:
                cmd.isAutoExecute = True
            except AttributeError:
                pass
            cmd.isExecutedWhenPreEmpted = False
            _pending_selection = []
            selections = _ui.activeSelections
            for i in range(selections.count):
                _pending_selection.append(selections.item(i).entity)
            on_execute = ExplodeExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception:
            if _ui:
                _ui.messageBox('Explode setup failed:\n{}'.format(traceback.format_exc()))


class ExplodeExecuteHandler(_CommandEventHandler):
    def notify(self, args):
        try:
            design = active_design()
            if not design:
                _ui.messageBox('Open a design before exploding fasteners.')
                return
            if not timeline_at_end(design):
                _ui.messageBox('Move the timeline marker to the end before exploding fasteners.')
                return
            if not _pending_selection:
                _ui.messageBox('Select one or more fasteners first.')
                return
            occurrences, skipped = resolve_to_occurrences(
                _pending_selection, design.rootComponent)
            distance_mm, adjusted = lift_distance_mm(_config)
            if adjusted:
                log('Configured explode.distance_mm was invalid; using {}mm'.format(distance_mm))
            exploded, engine_skipped = explode_occurrences(
                occurrences, mm_to_cm(distance_mm), design)
            for label, reason in skipped + engine_skipped:
                log('Skipped {}: {}'.format(label, reason))
            if exploded:
                log('Exploded {} fastener(s) by {}mm'.format(exploded, distance_mm))
            else:
                _ui.messageBox('Nothing to explode: all selected items were skipped '
                               '(see Text Commands palette).')
        except Exception:
            if _ui:
                _ui.messageBox('Explode failed:\n{}'.format(traceback.format_exc()))


class RestoreCreatedHandler(_CommandCreatedHandler):
    def notify(self, args):
        try:
            cmd = args.command
            try:
                cmd.isAutoExecute = True
            except AttributeError:
                pass
            cmd.isExecutedWhenPreEmpted = False
            on_execute = RestoreExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception:
            if _ui:
                _ui.messageBox('Restore setup failed:\n{}'.format(traceback.format_exc()))


class RestoreExecuteHandler(_CommandEventHandler):
    def notify(self, args):
        try:
            design = active_design()
            if not design:
                _ui.messageBox('Open a design before restoring fasteners.')
                return
            if not timeline_at_end(design):
                _ui.messageBox('Move the timeline marker to the end before restoring fasteners.')
                return
            restored = restore_all(design)
            if restored:
                log('Restored {} fastener(s)'.format(restored))
            else:
                log('Restore: nothing to restore')
        except Exception:
            if _ui:
                _ui.messageBox('Restore failed:\n{}'.format(traceback.format_exc()))


class FlipCreatedHandler(_CommandCreatedHandler):
    def notify(self, args):
        try:
            cmd = args.command
            try:
                cmd.isAutoExecute = True
            except AttributeError:
                pass
            cmd.isExecutedWhenPreEmpted = False
            on_execute = FlipExecuteHandler()
            cmd.execute.add(on_execute)
            _handlers.append(on_execute)
        except Exception:
            if _ui:
                _ui.messageBox('Flip setup failed:\n{}'.format(traceback.format_exc()))


class FlipExecuteHandler(_CommandEventHandler):
    def notify(self, args):
        try:
            design = active_design()
            if not design:
                _ui.messageBox('Open a design before flipping.')
                return
            if not timeline_at_end(design):
                _ui.messageBox('Move the timeline marker to the end before flipping.')
                return
            flipped, reason = flip_last_batch(design)
            if flipped:
                log('Flipped {} fastener(s)'.format(flipped))
            else:
                log('Flip: nothing to flip ({})'.format(reason))
        except Exception:
            if _ui:
                _ui.messageBox('Flip failed:\n{}'.format(traceback.format_exc()))
```

Also extend the guarded import at the top of `explode.py`: add `import traceback` next to `import math`, and inside the `try` add `_CommandCreatedHandler = adsk.core.CommandCreatedEventHandler` and `_CommandEventHandler = adsk.core.CommandEventHandler`, with the `except ImportError` branch setting both aliases to `object`. The handlers subclass these aliases (not `adsk.core.*` directly) so the module still imports under pytest — subclassing `adsk.core.*` when `adsk` is `None` raises `AttributeError` at class-definition time.

- [ ] **Step 2: Wire the module into the main file.** In `erikbuild-FusionDocumentationToolkit.py`:

(a) After the existing imports (line 10, after `import zlib`), add:

```python
import sys
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explode
```

(b) In `run()`, immediately after `init_capture_defaults()` (line 419), add:

```python
        importlib.reload(explode)
        explode.init(_app, _ui, _config)
```

(c) Change the `purge_stale_controls` call in `run()` (line 421) to include the new command IDs:

```python
        purge_stale_controls((CMD_ID, CAPTURE_CMD_ID, CONFIGURE_CAPTURE_CMD_ID,
                              explode.EXPLODE_CMD_ID, explode.RESTORE_CMD_ID,
                              explode.FLIP_CMD_ID))
```

(d) After the third `register_command` call in `run()` (line 450), add:

```python
        register_command(panel, explode.EXPLODE_CMD_ID, explode.EXPLODE_CMD_NAME,
                         explode.EXPLODE_CMD_DESCRIPTION,
                         os.path.join(resources_root, 'explodeFasteners'),
                         explode.ExplodeCreatedHandler())
        register_command(panel, explode.RESTORE_CMD_ID, explode.RESTORE_CMD_NAME,
                         explode.RESTORE_CMD_DESCRIPTION,
                         os.path.join(resources_root, 'restoreFasteners'),
                         explode.RestoreCreatedHandler())
        register_command(panel, explode.FLIP_CMD_ID, explode.FLIP_CMD_NAME,
                         explode.FLIP_CMD_DESCRIPTION,
                         os.path.join(resources_root, 'flipExplode'),
                         explode.FlipCreatedHandler())
```

(e) In `stop()`, change the `cmd_ids` tuple (line 460) to:

```python
        cmd_ids = (CMD_ID, CAPTURE_CMD_ID, CONFIGURE_CAPTURE_CMD_ID,
                   explode.EXPLODE_CMD_ID, explode.RESTORE_CMD_ID,
                   explode.FLIP_CMD_ID)
```

- [ ] **Step 3: Add the config section.** In `config.json`, after the `"capture"` object's closing brace (line 15), insert:

```json
    "explode": {
        "distance_mm": 20
    },
```

- [ ] **Step 4: Create placeholder icons** (proper artwork later via the PSD workflow in `design/`):

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && cp -r resources/capture resources/explodeFasteners && cp -r resources/capture resources/restoreFasteners && cp -r resources/capture resources/flipExplode
```

- [ ] **Step 5: Verify everything still imports and config parses**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -c "import json; json.load(open('config.json')); print('config ok')" && python3 -c "import explode; print('import ok')" && python3 -m pytest tests/test_explode_logic.py -q
```

Expected: `config ok`, `import ok`, 25 passed.

- [ ] **Step 6 [FUSION — Erik runs]: Smoke test.** Re-run the add-in (Utilities → Add-Ins → stop, then Run). Confirm: three new buttons appear on the DOCUMENTATION panel; clicking Restore in an empty design logs `[ExplodeFasteners] Restore: nothing to restore` to the palette; nothing crashes. Report back.

- [ ] **Step 7: Checkpoint — ask Erik to review and commit.** Suggested message: `Wire explode commands into the add-in.`

---

### Task 12: In-Fusion integration test (fixture builder + assertions)

**Files:**
- Create: `tests/fusion_integration/ExplodeIntegrationTest.py`
- Create: `tests/fusion_integration/ExplodeIntegrationTest.manifest`

The script builds its own fixture (plate with a through-hole screw+nut pair and a nested screw in a blind hole), exercises explode → flip → restore through the engine functions, and reports PASS/FAIL per assertion to the palette. It closes the fixture without saving.

- [ ] **Step 1: Write the manifest** at `tests/fusion_integration/ExplodeIntegrationTest.manifest`:

```json
{
    "autodeskProduct": "Fusion360",
    "type": "script",
    "scriptType": "python",
    "description": "Integration tests for the explode-fasteners feature."
}
```

- [ ] **Step 2: Write the test script** at `tests/fusion_integration/ExplodeIntegrationTest.py`:

```python
# ABOUTME: Self-contained in-Fusion integration test for the explode feature —
# ABOUTME: builds a fixture assembly, runs explode/flip/restore, asserts results.
import importlib
import math
import os
import sys
import traceback

import adsk.core
import adsk.fusion

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
import explode  # noqa: E402
importlib.reload(explode)  # pick up file edits even if the add-in cached the module

# Set from spike Finding 2: timeline items left after a copy's deleteMe in
# parametric mode. 0 when Finding 2 reported a clean timeline; bump to the
# observed residue otherwise so the restore assertion matches reality.
EXPECTED_TIMELINE_RESIDUE = 0

_results = []


def check(condition, label):
    _results.append((bool(condition), label))


def report(app):
    failures = [label for ok, label in _results if not ok]
    for ok, label in _results:
        app.log('[ExplodeTest] {} {}'.format('PASS' if ok else 'FAIL', label))
    app.log('[ExplodeTest] ==== {} passed, {} failed ===='.format(
        len(_results) - len(failures), len(failures)))


def extrude_profile(component, profile, distance_cm, operation):
    extrudes = component.features.extrudeFeatures
    inp = extrudes.createInput(profile, operation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(distance_cm))
    return extrudes.add(inp)


def build_plate(root):
    """6x4x0.5cm plate on the XY plane, top face at z=0.5, with two 0.17cm-radius
    through holes at x=+/-1.5 and one 0.14cm-radius blind hole (0.4 deep) at x=0."""
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(-3, -2, 0), adsk.core.Point3D.create(3, 2, 0))
    plate_profile = sketch.profiles.item(0)
    extrude_profile(root, plate_profile, 0.5,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

    hole_sketch = root.sketches.add(root.xYConstructionPlane)
    circles = hole_sketch.sketchCurves.sketchCircles
    circles.addByCenterRadius(adsk.core.Point3D.create(-1.5, 0, 0), 0.17)
    circles.addByCenterRadius(adsk.core.Point3D.create(1.5, 0, 0), 0.17)
    for i in range(hole_sketch.profiles.count):
        extrude_profile(root, hole_sketch.profiles.item(i), 0.5,
                        adsk.fusion.FeatureOperations.CutFeatureOperation)

    blind_sketch = root.sketches.add(root.xYConstructionPlane)
    # sketch on z=0 cutting upward into the plate from below is awkward; cut from
    # the top instead: offset construction plane at the plate top.
    planes = root.constructionPlanes
    plane_input = planes.createInput()
    plane_input.setByOffset(root.xYConstructionPlane, adsk.core.ValueInput.createByReal(0.5))
    top_plane = planes.add(plane_input)
    blind_sketch = root.sketches.add(top_plane)
    blind_sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), 0.14)
    extrude_profile(root, blind_sketch.profiles.item(0), -0.4,
                    adsk.fusion.FeatureOperations.CutFeatureOperation)


def build_screw(parent_occurrences, name, world_x, head_top_z, seat=True):
    """Simplified SHCS: shank r0.15 x 1.0 long pointing -Z from z=0, head r0.275
    x 0.3 tall above. When seat=True (root-level occurrences only) the screw is
    seated so the head bottom sits at z = head_top_z - 0.3. Native nested
    occurrences reject a transform2 override, so seat=False leaves the screw
    head-up at the component origin (placement doesn't affect the assertions)."""
    t = adsk.core.Matrix3D.create()
    occ = parent_occurrences.addNewComponent(t)
    comp = occ.component
    comp.name = name

    shank_sketch = comp.sketches.add(comp.xYConstructionPlane)
    shank_sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), 0.15)
    extrude_profile(comp, shank_sketch.profiles.item(0), -1.0,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

    head_sketch = comp.sketches.add(comp.xYConstructionPlane)
    head_sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), 0.275)
    extrude_profile(comp, head_sketch.profiles.item(0), 0.3,
                    adsk.fusion.FeatureOperations.JoinFeatureOperation)

    if seat:
        seat_m = adsk.core.Matrix3D.create()
        seat_m.translation = adsk.core.Vector3D.create(world_x, 0, head_top_z - 0.3)
        occ.transform2 = seat_m
    return occ


def build_square_nut(parent_occurrences, world_x, top_z):
    """0.55cm square nut, 0.24 thick, 0.125-radius bore, top face at top_z."""
    t = adsk.core.Matrix3D.create()
    occ = parent_occurrences.addNewComponent(t)
    comp = occ.component
    comp.name = 'SquareNut'

    sketch = comp.sketches.add(comp.xYConstructionPlane)
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(-0.275, -0.275, 0),
        adsk.core.Point3D.create(0.275, 0.275, 0))
    sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0, 0, 0), 0.125)
    ring_profile = None
    for i in range(sketch.profiles.count):
        if sketch.profiles.item(i).profileLoops.count == 2:
            ring_profile = sketch.profiles.item(i)
    extrude_profile(comp, ring_profile, -0.24,
                    adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

    seat = adsk.core.Matrix3D.create()
    seat.translation = adsk.core.Vector3D.create(world_x, 0, top_z)
    occ.transform2 = seat
    return occ


def world_z(occ):
    return occ.transform2.translation.z


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent
        explode.init(app, ui, {'explode': {'distance_mm': 20}})

        build_plate(root)
        # screw1 through hole at x=-1.5, head on plate top (z=0.5)
        screw1 = build_screw(root.occurrences, 'Screw1', -1.5, 0.8)
        # square nut under the same hole, coaxial with screw1, top face on plate bottom
        nut = build_square_nut(root.occurrences, -1.5, 0.0)
        # subassembly at x=+1.5 holding a nested, head-up screw. A nested
        # occurrence can't take a transform2 override, so Screw2 stays at the
        # subassembly origin — its placement doesn't affect the assertions,
        # which only check the copy's offset from the original.
        sub_t = adsk.core.Matrix3D.create()
        sub_t.translation = adsk.core.Vector3D.create(1.5, 0, 0)
        sub_occ = root.occurrences.addNewComponent(sub_t)
        sub_occ.component.name = 'SubAssembly'
        build_screw(sub_occ.component.occurrences, 'Screw2', -1.5, 0.8, seat=False)

        # root-context proxy for the nested screw
        screw2 = None
        for i in range(root.allOccurrences.count):
            o = root.allOccurrences.item(i)
            if o.component.name == 'Screw2':
                screw2 = o
        check(screw2 is not None, 'fixture: nested screw proxy found')

        timeline_before = design.timeline.count

        # --- selection resolution: a body proxy resolves to the deepest occurrence ---
        resolved, skipped = explode.resolve_to_occurrences(
            [screw2.bRepBodies.item(0)], root)
        check(len(resolved) == 1 and resolved[0].entityToken == screw2.entityToken,
              'resolution: nested body proxy -> deepest occurrence')

        # --- explode the batch: screw1 + nut + nested screw2 ---
        z_screw1, z_nut, z_screw2 = world_z(screw1), world_z(nut), world_z(screw2)
        count, eng_skipped = explode.explode_occurrences(
            [screw1, nut, screw2], 2.0, design)
        check(count == 3, 'explode: all three fasteners exploded (got {})'.format(count))
        check(len(eng_skipped) == 0, 'explode: nothing skipped')

        copies = explode.find_tagged_attributes(design, explode.ATTR_COPY)
        check(len(copies) == 3, 'explode: three tagged copies exist')
        check(not screw1.isLightBulbOn and not nut.isLightBulbOn and not screw2.isLightBulbOn,
              'explode: originals hidden')

        by_original = {}
        for attr in copies:
            by_original[attr.value] = adsk.fusion.Occurrence.cast(attr.parent)
        copy_s1 = by_original[screw1.entityToken]
        copy_nut = by_original[nut.entityToken]
        copy_s2 = by_original[screw2.entityToken]
        check(abs(world_z(copy_s1) - (z_screw1 + 2.0)) < 1e-5,
              'explode: screw1 head-up lift is +Z by 2.0 (got dz={:.4f})'.format(
                  world_z(copy_s1) - z_screw1))
        # The square nut has no distinct head, so v1 picks the sign from the
        # +axis fallback — direction isn't determinable, only that it lifts the
        # full distance along its (Z) axis. Flip is what gets it the right way.
        check(abs(abs(world_z(copy_nut) - z_nut) - 2.0) < 1e-5,
              'explode: nut lifts 2.0 along its axis via fallback (got dz={:.4f})'.format(
                  world_z(copy_nut) - z_nut))
        check(abs(world_z(copy_s2) - (z_screw2 + 2.0)) < 1e-5,
              'explode: nested screw lifts +Z (got dz={:.4f})'.format(
                  world_z(copy_s2) - z_screw2))
        check(copy_s2.assemblyContext is None,
              'explode: nested screw copy landed in root')
        check(copy_s1.isLightBulbOn and copy_nut.isLightBulbOn and copy_s2.isLightBulbOn,
              'explode: copies are visible')

        # --- double explode is skipped (the guard lives in resolve_to_occurrences,
        # which is what the command handler feeds the engine from) ---
        resolved2, skipped2 = explode.resolve_to_occurrences([screw1], root)
        check(len(resolved2) == 0 and len(skipped2) == 1 and skipped2[0][1] == 'already exploded',
              'double explode: resolution skips tagged original')

        # --- flip mirrors the batch ---
        flipped, reason = explode.flip_last_batch(design)
        check(flipped == 3, 'flip: all three flipped (got {}, reason={})'.format(flipped, reason))
        copies_after_flip = explode.find_tagged_attributes(design, explode.ATTR_COPY)
        by_original = {}
        for attr in copies_after_flip:
            by_original[attr.value] = adsk.fusion.Occurrence.cast(attr.parent)
        check(abs(world_z(by_original[screw1.entityToken]) - (z_screw1 - 2.0)) < 1e-5,
              'flip: screw1 copy now at -Z offset')
        check(by_original[screw1.entityToken].isLightBulbOn,
              'flip: flipped copy is visible')
        flipped_back, _ = explode.flip_last_batch(design)
        check(flipped_back == 3, 'flip: second flip returns to first guess')
        by_original = {}
        for attr in explode.find_tagged_attributes(design, explode.ATTR_COPY):
            by_original[attr.value] = adsk.fusion.Occurrence.cast(attr.parent)
        check(abs(world_z(by_original[screw1.entityToken]) - (z_screw1 + 2.0)) < 1e-5,
              'flip: copy back at +Z offset')

        # --- restore ---
        restored = explode.restore_all(design)
        check(restored == 3, 'restore: three copies removed (got {})'.format(restored))
        check(len(explode.find_tagged_attributes(design, explode.ATTR_COPY)) == 0,
              'restore: no copy tags remain')
        check(len(explode.find_tagged_attributes(design, explode.ATTR_ORIGINAL)) == 0,
              'restore: no original tags remain')
        check(screw1.isLightBulbOn and nut.isLightBulbOn and screw2.isLightBulbOn,
              'restore: originals visible again')
        check(design.timeline.count == timeline_before + EXPECTED_TIMELINE_RESIDUE,
              'restore: timeline as expected per spike Finding 2 ({} vs {}+{})'.format(
                  design.timeline.count, timeline_before, EXPECTED_TIMELINE_RESIDUE))
        flipped_after, reason_after = explode.flip_last_batch(design)
        check(flipped_after == 0 and reason_after == 'no explode batch this session',
              'flip after restore: no-op')

        # --- direct-modeling mode: explode/restore still work without a timeline ---
        design.designType = adsk.fusion.DesignTypes.DirectDesignType
        count3, _ = explode.explode_occurrences([screw1], 2.0, design)
        check(count3 == 1, 'direct mode: explode works')
        check(explode.restore_all(design) == 1, 'direct mode: restore works')

        report(app)
        doc.close(False)
    except Exception:
        report(app)
        if ui:
            ui.messageBox('Integration test crashed:\n{}'.format(traceback.format_exc()))
```

- [ ] **Step 3 [FUSION — Erik runs]: Run the integration test.** Scripts tab → “+” → `tests/fusion_integration/` → run **ExplodeIntegrationTest**. Paste every `[ExplodeTest]` line back.

- [ ] **Step 4: Fix failures using superpowers:systematic-debugging.** For each FAIL line: form a single hypothesis, make the smallest change, have Erik re-run the script, verify. Do not stack fixes. Repeat until the summary line reports 0 failed.

- [ ] **Step 5: Checkpoint — ask Erik to review and commit.** Suggested message: `Add in-Fusion integration tests for explode feature.`

---

### Task 13: Live verification and README

**Files:**
- Modify: `README.md:34-41` (Use table), `:42-52` (Configuration section)

- [ ] **Step 1 [FUSION — Erik runs]: Real-world verification on an actual project.** In one of Erik's real designs: select a few fasteners (including one inside a subassembly and one nut if available), hotkey or click **Explode Fasteners**, screenshot with **Capture Image**, try **Flip Last Explode**, then **Restore Fasteners**. Confirm: lift directions look right (expect headless fasteners like nuts to sometimes need a Flip — that's the v1 design), holes read as empty, restore leaves the design exactly as before (check the timeline tail). Report anything surprising.

- [ ] **Step 2 [FUSION — Erik runs]: Cross-session persistence check.** This is the one feature claim no automated test covers. Explode a couple of fasteners, **save** the document, **close** it, **reopen** it, then press **Restore Fasteners**. Confirm the copies are removed and originals unhidden — i.e. the tags survived the save/reopen. Report the result.

- [ ] **Step 3: Update the README Use table.** Add three rows after the Configure Capture row:

```markdown
| **Explode Fasteners** | Copies the selected fasteners 20mm out along their insertion axes and hides the originals — empty-hole shots without moving the assembly. Direction is inferred from the fastener's geometry. |
| **Flip Last Explode** | Re-lifts the most recent explode batch to the opposite side, for when the direction guess is wrong. |
| **Restore Fasteners** | Deletes all exploded copies and unhides the originals, across every outstanding batch. |
```

- [ ] **Step 4: Update the README Configuration section.** Add to the notable-keys list:

```markdown
- `explode.distance_mm` — how far Explode Fasteners lifts copies (default `20`, clamped 1–500).
```

- [ ] **Step 5: Run the full pytest suite one final time**

```bash
cd /Users/erik/Code/FusionDocumentationToolkit && python3 -m pytest tests/ -v
```

Expected: 25 passed.

- [ ] **Step 6: Checkpoint — ask Erik to review and commit.** Suggested message: `Document explode commands in README.`

- [ ] **Step 7: Finish the branch.** Use superpowers:finishing-a-development-branch to decide merge/PR/cleanup with Erik.

---

## Verification Summary (Definition of Done)

- All pytest tests pass: `python3 -m pytest tests/ -v` → 25 passed, pristine output.
- Integration script reports 0 failed in both parametric and direct fixtures (with the timeline assertion set to match spike Finding 2).
- All five spike findings recorded in Task 2 and consistent with shipped code.
- Three buttons live on the DOCUMENTATION panel; explode → capture → restore round-trips cleanly on a real design, and survives a save/close/reopen (Task 13 Steps 1–2).
- README and config.json document the feature.
- Every commit made by Erik; no agent commits.
