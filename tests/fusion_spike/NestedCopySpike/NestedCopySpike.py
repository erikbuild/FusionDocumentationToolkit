# ABOUTME: Diagnoses copyToComponent's coordinate frame for a NESTED occurrence,
# ABOUTME: to fix body-copy positioning for externally-linked fasteners.
import adsk.core
import adsk.fusion
import traceback


def log(app, m):
    app.log('[NestedCopySpike] ' + m)


def bb(b):
    lo, hi = b.minPoint, b.maxPoint
    return '({:.2f},{:.2f},{:.2f})..({:.2f},{:.2f},{:.2f})'.format(
        lo.x, lo.y, lo.z, hi.x, hi.y, hi.z)


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    try:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Sub at world (10,0,0); Inner (identity in Sub) with a box sketched at
        # native (0,5)-(1,6) extruded +1 -> native (0,5,0)..(1,6,1),
        # world (10,5,0)..(11,6,1). Native x (~0) differs from world x (~10).
        sub_t = adsk.core.Matrix3D.create()
        sub_t.translation = adsk.core.Vector3D.create(10.0, 0, 0)
        sub = root.occurrences.addNewComponent(sub_t)
        sub.component.name = 'Sub'
        inner = sub.component.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        inner.component.name = 'Inner'
        sk = inner.component.sketches.add(inner.component.xYConstructionPlane)
        sk.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 5, 0), adsk.core.Point3D.create(1, 6, 0))
        ext = inner.component.features.extrudeFeatures
        ext.addSimple(sk.profiles.item(0), adsk.core.ValueInput.createByReal(1.0),
                      adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

        proxy = None
        for i in range(root.allOccurrences.count):
            if root.allOccurrences.item(i).component.name == 'Inner':
                proxy = root.allOccurrences.item(i)
        pt = proxy.transform2.translation
        log(app, 'proxy.transform2.translation=({:.2f},{:.2f},{:.2f})'.format(pt.x, pt.y, pt.z))
        log(app, 'SOURCE proxy body world bbox {}'.format(bb(proxy.bRepBodies.item(0).boundingBox)))

        # FRAME TEST: copy into an identity target, measure where it lands.
        t1 = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        proxy.bRepBodies.item(0).copyToComponent(t1)
        raw = t1.bRepBodies.item(0).boundingBox
        frame = ('NATIVE (x~0, occurrence transform stripped)' if raw.minPoint.x < 5
                 else 'WORLD (x~10, assembly transform already baked in)')
        log(app, 'COPY raw (target@identity) world bbox {} -> {}'.format(bb(raw), frame))

        # POSITIONING TEST: replicate the current fallback
        # (target.transform2 = proxy.transform2 + Z2). Correct landing = (10,5,2)..(11,6,3).
        t2 = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        proxy.bRepBodies.item(0).copyToComponent(t2)
        m = proxy.transform2.copy()
        tr = m.translation
        tr.z += 2.0
        m.translation = tr
        t2.transform2 = m
        got = t2.bRepBodies.item(0).boundingBox
        ok = abs(got.minPoint.x - 10.0) < 1e-6 and abs(got.minPoint.z - 2.0) < 1e-6
        log(app, 'FALLBACK copy world bbox {} (expected (10,5,2)..(11,6,3)) -> {}'.format(
            bb(got), 'CORRECT' if ok else 'WRONG — proxy.transform2 double-applies'))

        doc.close(False)
        log(app, 'Spike complete. Paste all [NestedCopySpike] lines back.')
    except Exception:
        if ui:
            ui.messageBox('NestedCopySpike failed:\n{}'.format(traceback.format_exc()))
