# Explode Fasteners for Documentation — Design Spec

**Date:** 2026-06-09
**Status:** Approved design, pre-implementation
**Background research:** `research/2026-06-09_fastener-move-copy-feasibility.md` (API claims verified against Autodesk docs and forums)

## Purpose

Automate the manual documentation chore of repositioning fasteners for assembly-manual screenshots. Today the user selects fasteners and runs Fusion's Move/Copy to lift them 15–20mm out of their holes, screenshots the result, then puts everything back. This feature reduces that to one hotkey press before the screenshot and one after.

## User Workflow

1. Select one or more fasteners — browser occurrence picks or canvas face/body picks, at any nesting depth.
2. Press **Explode Fasteners** (hotkey-assignable). For each selected fastener: a copy appears lifted along its insertion axis at the configured distance, and the seated original is hidden — so the hole appears empty while the assembly never actually moves.
3. If the lift direction guessed wrong, press **Flip Last Explode** to mirror the most recent batch to the other side.
4. Screenshot with the existing **Capture Image** command.
5. Press **Restore Fasteners**: all copies are deleted and all originals unhidden, across every outstanding explode batch.

Multiple explode batches may be outstanding at once (explode A, explode B, screenshot, restore everything).

## Commands

Three new silent commands on the DOCUMENTATION panel, registered through the existing `register_command` pattern with the `isAutoExecute` no-dialog treatment used by Capture Image:

| Command ID | Name | Behavior |
|---|---|---|
| `ExplodeFastenersCmd` | Explode Fasteners | Copy + lift selected occurrences, hide originals |
| `RestoreFastenersCmd` | Restore Fasteners | Delete all tagged copies, unhide all originals |
| `FlipLastExplodeCmd` | Flip Last Explode | Re-lift the most recent batch in the opposite direction |

Selection contract: the commands operate on **whatever occurrences the user selected** — there is no fastener auto-detection (the API offers none; name heuristics are brittle). Pre-selection is read from `ui.activeSelections` inside the `commandCreated` handler (it does not survive into later command events) and stashed for `execute`.

Each command gets an icon set under `resources/<commandName>/` (16/32/64 px). Placeholder icons initially; proper artwork follows the existing PSD workflow in `design/`.

## Explode Algorithm

The command runs in two phases: **inference first, mutation second**. All axis and sign decisions for the whole batch are computed before any copy is created or any original hidden, so the result never depends on the order fasteners are processed or on a half-mutated scene.

### Phase A — resolve and infer (read-only)

For each entity in the selection:

1. **Resolve to a fastener occurrence.** Canvas picks return BRepFace/BRepBody proxies; browser picks return occurrences. Resolve every pick to the occurrence that directly owns the geometry — the *deepest* occurrence in the path, not the top-level subassembly (`Selection.entity.assemblyContext` alone returns the top-level occurrence and is insufficient for nested fasteners; the resolution mechanism is spike item 3). Dedupe occurrences across picks. Skip, with a palette log line each:
   - occurrences tagged `explodedCopy` (don't explode a copy);
   - occurrences tagged `explodedOriginal` (already exploded — log "already exploded");
   - picks that resolve to no occurrence at all (geometry modeled directly in the root component).

2. **Infer the lift axis** (Approach C — geometry-driven with convention fallback). The axis is **unsigned**; the sign is chosen in step 3.
   - Collect the cylindrical and conical faces of the occurrence's bodies, in world space (via proxies).
   - Bucket face axes by direction — two axes share a bucket when the angle between them, or between one and the other's opposite, is ≤ 1.0° — summing face area per bucket.
   - The direction with the largest summed area is the axis. This finds the shank/thread axis on screws and the threaded-hole axis on nuts, regardless of how the library modeled the part.
   - If no cylindrical or conical faces exist (square nuts without modeled holes, printed clips), fall back to the occurrence's world-space local-Z axis.

3. **Pick the sign** (which way is "out" — no API provides this). In order:
   - **Head-end heuristic (primary).** Among the faces coaxial with the chosen axis, the largest-radius one marks the head OD; the body end nearest it is the head end, and the sign points from the body center toward that end. ("Out" is always toward the head for seated screws, bolts, and flanged inserts, including counterbored ones.) Inapplicable when the coaxial radii are all equal within tolerance (nuts, dowels, set screws) or the axis came from the local-Z fallback.
   - **Fallback:** +axis. Flip Last Explode is the user-level escape hatch — for fasteners with no distinct head (nuts, dowels, set screws), the first guess may point the wrong way and the user presses Flip. A geometry-driven tie-breaker (the offset ring-ray test) is planned for v2 to get those right on the first press; see Out of Scope.

### Phase B — mutate

Runs only after Phase A has produced an axis, sign, and distance for every surviving item. If Phase A leaves no items at all, behave exactly like an empty selection (message box; see Error Handling).

4. **Create each copy.** `rootComponent.occurrences.addExistingComponent(occ.component, T)` where `T` is the original's world transform pre-multiplied by a translation of `sign × axis × distance`. Copies always land in the **root component** — adding them to a nested parent would edit that component's definition and duplicate the copy into every instance of the subassembly. The lift offset is part of the creation transform; the copy's transform is never edited afterward, so no Capture Position / snapshot machinery is needed in parametric mode.

5. **Hide each original** (`isLightBulbOn = False`).

6. **Tag for tracking** with persistent attributes (group `FusionDocumentationToolkit`):
   - on the copy: `explodedCopy` = entity token of the original occurrence;
   - on the original: `explodedOriginal` = `'1'`.
   Attributes and entity tokens persist in the saved document, so Restore works even after closing and reopening Fusion with fasteners left exploded.

7. **Record the batch in session memory** for Flip: the identity of the document the batch belongs to, plus, per fastener, the original's entity token, unsigned axis, chosen sign, and distance. (Copies are *not* tracked by reference in memory — Flip locates them through their `explodedCopy` attributes; see Flip Algorithm.)

All mutations happen inside the command's `execute` handler, so each explode is a single undo transaction.

## Restore Algorithm

1. Find all occurrences tagged `explodedCopy` (`design.findAttributes`); for each, delete the copy and unhide the original resolved from the stored entity token. If a stored token no longer resolves (original deleted while exploded), delete the copy anyway, log the unresolvable original, and continue.
2. Find any occurrences still tagged `explodedOriginal` (covers a copy the user deleted manually) and unhide them.
3. Remove the `explodedOriginal` tags; clear the session's last-batch memory.
4. Log a restored count to the Text Commands palette; if nothing was found, log a no-op message.

Single undo transaction. Restores all outstanding batches regardless of which session created them.

## Flip Algorithm

Flip is **delete-and-re-explode with negated sign**, not a transform edit — editing an occurrence transform after creation would create a pending Capture Position state in parametric mode, which this design deliberately avoids.

1. If no batch exists in session memory, or the batch belongs to a different document than the active one, log a no-op and stop.
2. Locate the batch's copies by querying `explodedCopy` attributes and matching their stored values against the batch's original tokens (robust to anything that invalidated direct references). Delete the located copies; skip batch entries whose copy is missing.
3. Recreate each copy at `original world transform + (−sign × axis × distance)`, re-assert the original's hidden state (covers a stray undo between explode and flip), retag, and negate the sign stored in memory. Entries whose original token no longer resolves are dropped from the batch with a log line.
4. Pressing Flip again flips back.

Last-batch memory is per-session by design: flipping is something you do immediately after an explode you are looking at.

## Configuration

New `config.json` section:

```json
"explode": {
    "distance_mm": 20
}
```

- `distance_mm` — lift distance in millimeters, clamped to 1–500. Clamping happens silently at config load, with a palette log line when the configured value was out of range. Converted to centimeters at the API boundary (the Fusion API's internal unit is cm; 20mm = 2.0).

No other knobs in v1: originals are always hidden, copies always land in root, and the silent-command pattern cannot take per-run input.

## Code Organization

- New module `explode.py` beside the main file (the main file is already ~660 lines; this feature would push it past 1,000).
- `explode.py` separates pure decision logic from API access:
  - **Pure functions** operating on plain data (tuples/dicts): axis bucketing and selection, head-end heuristic, the lift-sign decision, mm→cm conversion and clamping. These run under pytest with synthetic data — no `adsk` imports.
  - **Fusion adapter functions**: selection resolution, face/axis extraction, copy creation, attribute tagging, visibility. These touch `adsk` and are exercised by the in-Fusion test script.
- The main file registers the three commands and delegates to `explode.py`. Both files carry ABOUTME headers.

## Error Handling

- Empty selection — or a batch where Phase A skips every item — → message box ("Select one or more fasteners first." / "Nothing to explode: all selected items were skipped (see Text Commands palette)."). Skipped-item details always go to the palette.
- An item whose axis cannot be inferred or whose copy creation fails (`addExistingComponent` returning null) → skipped with a palette log line naming the component; the rest of the batch proceeds.
- Parametric mode with the timeline marker rolled back from the end → the explode/restore/flip command aborts with a message box (API operations would land mid-history); the user moves the marker to the end and retries.
- Restore/Flip with nothing to do → palette log no-op, no dialog.
- All logging uses the Text Commands palette with an `[ExplodeFasteners] ` prefix, matching the existing `[CaptureImage] ` convention.
- Jointed or grounded originals are a non-issue: originals never move.

## Parametric vs Direct Mode

Copy creation and deletion are ordinary operations in both modes. No snapshots are ever needed because no occurrence transform is edited after creation (Flip recreates instead of moving). In parametric mode the copy adds a timeline item; `deleteMe` is expected to remove it cleanly — verified by the spike below. The rolled-back-timeline guard above applies to parametric mode only.

## Pre-Implementation Spike

Five API behaviors were flagged as undocumented or single-sourced in the research and must be verified in Fusion before implementation:

1. **`addExistingComponent` transform coordinate space** — assumed root-relative when called on `rootComponent.occurrences`; verify with a nested original.
2. **`deleteMe` timeline behavior in parametric mode** — verify the copy's create item is removed (timeline ends clean after restore) rather than leaving a create/remove pair.
3. **Deepest-occurrence resolution from a canvas pick** — verify a mechanism for resolving a BRepFace/BRepBody proxy to the occurrence that directly owns it (candidate approaches: walking the proxy's `assemblyContext` path, or matching `nativeObject.parentComponent` against `allOccurrencesByComponent` along the path).
4. **Attribute round-trip on occurrences** — Restore and Flip rest entirely on this: verify that attributes added to an *occurrence* (not a component) are returned by `design.findAttributes`, that `attribute.parent` casts back to the occurrence, and that a stored entity-token value round-trips. If this fails, the whole tracking design must change.
5. **Head-end geometry from proxy faces** — with the ring-ray tie-breaker deferred, the head-end heuristic is the only sign source, so verify its inputs in the proxy context: that a nested fastener's cylindrical face `geometry` (axis, origin, radius) reads back in **world space**, and that the larger-radius (head) face's `origin` projects measurably farther along the axis than the shank's — i.e. the surface origin actually distinguishes the head end. If the origins coincide, the heuristic needs a different axial reference (face bounding box or evaluator) before Task 6.

Spike findings get recorded in the implementation plan before the relevant tasks are finalized.

## Testing

- **Unit (pytest, outside Fusion):** the pure functions — axis bucketing (parallel/antiparallel grouping, area summing, the 1.0° tolerance edges), head-end heuristic (clear head; all-equal radii → inapplicable; fallback-axis case → inapplicable), the lift-sign decision (head-end wins, +axis fallback), config parsing and clamping. Synthetic face data; no Fusion required.
- **Integration / E2E (inside Fusion):** a test script run from Fusion's script environment that **builds its own fixture document programmatically** (a plate with through and blind holes, screws at root level and inside a subassembly, a screw+nut pair on a shared axis, a square nut), runs explode/flip/restore against it, and asserts: copy positions and lift directions (headed screws lift head-out by the head-end heuristic; the square nut has no distinct head, so v1 lifts it via the +axis fallback — the test asserts lift magnitude along the axis, not direction, and that Flip reverses it), original visibility states, attribute tags, restore completeness, double-explode of the same fastener being skipped, and (parametric mode) the timeline cleanliness established by spike Finding 2. Reports pass/fail to the Text Commands palette and closes the fixture without saving. Run in both parametric and direct-modeling fixture modes. Fusion has no headless mode, so this is launched manually in-app, but it is fully self-contained and deterministic.
- **Cross-session persistence (manual):** explode, save, close, reopen the document, then Restore — confirm the tags persist and Restore still finds everything. This is the one feature claim no automated path covers (the integration test is single-session).

## Out of Scope (v1)

- Offset ring-ray sign tie-breaker. v1 picks the sign from the head-end heuristic and falls back to +axis; headless fasteners (nuts, dowels, set screws) may guess wrong and need one Flip. v2 adds the ring-ray test (cast a ring of rays parallel to the axis from just outside each end, the side with neighboring material is "in") to get those right on the first press.
- Joint-based axis inference (this project's fasteners are placed without joints; the geometry path covers them).
- Move semantics for the originals (copy + hide achieves the empty-hole shot without touching the assembly).
- Per-run distance or direction UI; hide-originals toggle.
- Fastener auto-detection or filtering of the selection.
- Collision/clearance checking of the lifted position.
- General undo-interleaving recovery: beyond Flip re-asserting hidden originals, sequences like "explode, Ctrl+Z, flip" are not specially handled — Restore's attribute scan is the universal cleanup.

## Known Side Effects

- While exploded, each copied fastener is an extra instance of its component — part counts in BOMs or instance-count tooling are +N until restored.
- A document saved while exploded and later reopened loses nothing: tags persist with the saved document, so Restore still finds everything.
