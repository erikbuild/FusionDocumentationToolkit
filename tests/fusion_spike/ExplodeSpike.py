# ABOUTME: One-shot Fusion script that verifies five API behaviors the
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
        # entityToken is only valid for proxies whose top-level parent is the root,
        # which is exactly what the real design tags (selections + addExistingComponent
        # copies). Mirror that: tag the root-context proxy as the original, a root-level
        # occurrence as the stand-in copy, store the original's token, and confirm the
        # full findAttributes -> value -> findEntityByToken round-trip restore_all relies on.
        GROUP = 'FusionDocumentationToolkit'
        original = nested_proxy   # root-context proxy, like a selected nested fastener
        copy_stub = sub_occ       # root-level occurrence, stand-in for the lifted copy
        original.attributes.add(GROUP, 'spikeOriginal', '1')
        copy_stub.attributes.add(GROUP, 'spikeCopy', original.entityToken)
        found_orig = design.findAttributes(GROUP, 'spikeOriginal')
        found_copy = design.findAttributes(GROUP, 'spikeCopy')
        n_orig = len(found_orig) if found_orig else 0
        n_copy = len(found_copy) if found_copy else 0
        parent_ok = bool(n_copy and adsk.fusion.Occurrence.cast(found_copy[0].parent))
        value_ok = bool(n_copy and found_copy[0].value == original.entityToken)
        resolved = design.findEntityByToken(original.entityToken) if value_ok else None
        resolved_occ = adsk.fusion.Occurrence.cast(resolved[0]) if resolved and len(resolved) > 0 else None
        resolve_ok = bool(resolved_occ and resolved_occ.fullPathName == original.fullPathName)
        log(app, 'FINDING 4 (occurrence attributes): findAttributes -> {} original, {} copy; '
                 'parent->Occurrence={}, value round-trips={}, token resolves back={} -> {}'.format(
                     n_orig, n_copy, parent_ok, value_ok, resolve_ok,
                     'ATTRIBUTES WORK' if (n_orig and n_copy and parent_ok and value_ok and resolve_ok)
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

        # --- Finding 5d: face bounding box distinguishes the head end (the 5c fix) ---
        # Surface origins coincide, so the revised head_end_sign uses each face's bbox
        # center as its axial position. Confirm the head (max-radius) face's bbox center
        # lands on the head side of the body's bbox center.
        zlo = min(screw_proxy.bRepBodies.item(i).boundingBox.minPoint.z
                  for i in range(screw_proxy.bRepBodies.count))
        zhi = max(screw_proxy.bRepBodies.item(i).boundingBox.maxPoint.z
                  for i in range(screw_proxy.bRepBodies.count))
        body_cz = (zlo + zhi) / 2.0
        head_face = None
        head_r = -1.0
        for bi in range(screw_proxy.bRepBodies.count):
            b = screw_proxy.bRepBodies.item(bi)
            for fi in range(b.faces.count):
                f = b.faces.item(fi)
                if (f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType
                        and f.geometry.radius > head_r):
                    head_r = f.geometry.radius
                    head_face = f
        if head_face:
            hb = head_face.boundingBox
            head_cz = (hb.minPoint.z + hb.maxPoint.z) / 2.0
            log(app, 'FINDING 5d: body bbox center z={:.3f}, head face (r={:.3f}) bbox center z={:.3f}, '
                     'delta={:.4f} -> {}'.format(
                         body_cz, head_r, head_cz, head_cz - body_cz,
                         'HEAD-END DISTINGUISHABLE via face bbox (head above center, +Z correct)'
                         if head_cz - body_cz > 1e-4
                         else 'STILL AMBIGUOUS — rethink head_end_sign'))
        else:
            log(app, 'FINDING 5d: no cylindrical head face found — STOP AND REVISE')

        doc.close(False)
        log(app, 'Spike complete. Paste all [ExplodeSpike] lines back to the agent.')
    except Exception:
        if ui:
            ui.messageBox('Spike failed:\n{}'.format(traceback.format_exc()))
