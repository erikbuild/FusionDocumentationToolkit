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
        by_original = {}
        for attr in explode.find_tagged_attributes(design, explode.ATTR_COPY):
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
