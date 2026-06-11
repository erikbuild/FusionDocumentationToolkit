# ABOUTME: Verifies BRepBody.copyToComponent (coordinate space + appearance)
# ABOUTME: for the externally-linked-fastener copy fallback in explode.py.
import adsk.core
import adsk.fusion
import traceback


def log(app, msg):
    app.log('[LinkedCopySpike] ' + msg)


def bbox_str(b):
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

        # Source box inside an occurrence seated at world (5, 0, 3).
        src_occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        src_occ.component.name = 'Source'
        sk = src_occ.component.sketches.add(src_occ.component.xYConstructionPlane)
        sk.sketchCurves.sketchLines.addTwoPointRectangle(
            adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(1, 1, 0))
        ext = src_occ.component.features.extrudeFeatures
        ext.addSimple(sk.profiles.item(0), adsk.core.ValueInput.createByReal(1.0),
                      adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        seat = adsk.core.Matrix3D.create()
        seat.translation = adsk.core.Vector3D.create(5.0, 0, 3.0)
        src_occ.transform2 = seat

        src_body = src_occ.bRepBodies.item(0)
        log(app, 'SOURCE world bbox {} appearance={!r}'.format(
            bbox_str(src_body.boundingBox),
            src_body.appearance.name if src_body.appearance else None))

        # Copy the source body into a fresh root-level component at identity.
        target = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        target.component.name = 'CopyTarget'
        new_body = src_body.copyToComponent(target)
        log(app, 'copyToComponent returned a body: {}'.format(new_body is not None))

        copy_body = target.bRepBodies.item(0)  # world-space proxy
        same_world = (abs(copy_body.boundingBox.minPoint.x - src_body.boundingBox.minPoint.x) < 1e-6
                      and abs(copy_body.boundingBox.minPoint.z - src_body.boundingBox.minPoint.z) < 1e-6)
        log(app, 'COPY (target@identity) world bbox {} -> {}'.format(
            bbox_str(copy_body.boundingBox),
            'WORLD-PRESERVED (sits on source)' if same_world else 'RE-BASED to target origin'))
        log(app, 'COPY appearance={!r} -> {}'.format(
            copy_body.appearance.name if copy_body.appearance else None,
            'APPEARANCE KEPT' if copy_body.appearance else 'appearance lost (would render default)'))

        # Lift: set the target occurrence's transform and confirm the copy moves.
        z_before = target.bRepBodies.item(0).boundingBox.minPoint.z
        lift = adsk.core.Matrix3D.create()
        lift.translation = adsk.core.Vector3D.create(0, 0, 2.0)
        target.transform2 = lift
        z_after = target.bRepBodies.item(0).boundingBox.minPoint.z
        log(app, 'LIFT via target.transform2 (+Z2): copy z {:.2f} -> {:.2f} -> {}'.format(
            z_before, z_after,
            'TARGET TRANSFORM LIFTS COPY' if abs(z_after - (z_before + 2.0)) < 1e-6
            else 'did NOT lift as expected'))

        doc.close(False)
        log(app, 'Spike complete. Paste all [LinkedCopySpike] lines back.')
    except Exception:
        if ui:
            ui.messageBox('LinkedCopySpike failed:\n{}'.format(traceback.format_exc()))
