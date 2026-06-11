# ABOUTME: Explode/restore/flip of fastener occurrences for documentation
# ABOUTME: screenshots — pure decision logic plus Fusion API adapters.

import math
import traceback

try:
    import adsk.core
    import adsk.fusion
    _CommandCreatedHandler = adsk.core.CommandCreatedEventHandler
    _CommandEventHandler = adsk.core.CommandEventHandler
except ImportError:
    adsk = None  # pure decision functions stay importable under pytest
    _CommandCreatedHandler = object   # handlers never run under pytest
    _CommandEventHandler = object


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


def has_tag(occ, attr_name):
    try:
        return occ.attributes.itemByName(ATTR_GROUP, attr_name) is not None
    except Exception:
        return False


def resolve_to_occurrences(entities, root):
    """Map raw selection entities (occurrences, or face/body proxies from
    canvas picks) to the deepest occurrences owning them, deduped and with
    already-exploded items filtered out. Returns (occurrences, skipped) where
    skipped is a list of (label, reason) for palette logging.

    Only root-context occurrences carry entity tokens (spike Finding 4), which
    is what both selection paths yield: UI picks are root-context, and
    allOccurrencesByComponent returns root-context proxies."""
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


# ---------------------------------------------------------------------------
# Command handlers — registered by the main add-in file.
# ---------------------------------------------------------------------------

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
