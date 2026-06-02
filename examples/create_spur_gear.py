"""
Involute Spur Gear Generator
==============================
Creates a true involute spur gear in Fusion 360.

Parameters (editable):
  - module_val: tooth size in cm (0.3 = 3mm)
  - teeth: number of teeth
  - thickness: gear thickness in cm
  - shaft_radius: center hole radius in cm

Method: Blank cylinder + cut one tooth space + circular pattern.
Each tooth space is a properly closed 6-curve loop:
  1. radial line (root → base circle)
  2. involute spline (base → addendum)
  3. addendum arc
  4. involute spline (addendum → base, reversed)
  5. radial line (base → root)
  6. root arc

Author: Claude AI Assistant
License: MIT
"""

import adsk.core, adsk.fusion
import math

app = adsk.core.Application.get()
ui = app.userInterface

# Create a fresh document
doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
design = adsk.fusion.Design.cast(app.activeProduct)
rt = design.rootComponent
extrudes = rt.features.extrudeFeatures

# ---------------------------------------------------------------------------
# Parameters (all in cm — Fusion 360 internal unit)
# ---------------------------------------------------------------------------
module_val = 0.3        # 3 mm
teeth = 20
thickness = 1.0         # 10 mm
shaft_radius = 0.4      # 8 mm diameter hole

pitch_radius = module_val * teeth / 2.0
base_radius  = pitch_radius * math.cos(math.radians(20))
outer_radius = pitch_radius + module_val
root_radius  = pitch_radius - 1.25 * module_val
center = adsk.core.Point3D.create(0, 0, 0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_coll(pts):
    """Convert list of Point3D to ObjectCollection."""
    c = adsk.core.ObjectCollection.create()
    for p in pts: c.add(p)
    return c

def involute_xy(rb, theta):
    """Involute of a circle at base radius rb, roll angle theta."""
    return (rb*(math.cos(theta)+theta*math.sin(theta)),
            rb*(math.sin(theta)-theta*math.cos(theta)))

def short_sweep(p_from, p_to):
    """Angular distance from p_from to p_to, short way (-pi to +pi)."""
    d = math.atan2(p_to.y, p_to.x) - math.atan2(p_from.y, p_from.x)
    if d > math.pi: d -= 2*math.pi
    elif d < -math.pi: d += 2*math.pi
    return d

# ---------------------------------------------------------------------------
# Step 1: Blank cylinder (addendum diameter)
# ---------------------------------------------------------------------------
sk1 = rt.sketches.add(rt.xYConstructionPlane)
sk1.name = "Gear Blank"
sk1.sketchCurves.sketchCircles.addByCenterRadius(center, outer_radius)

ei = extrudes.createInput(
    sk1.profiles.item(0),
    adsk.fusion.FeatureOperations.NewBodyFeatureOperation
)
ei.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness))
blank = extrudes.add(ei)
blank.name = "Gear Blank"
print(f"Blank created: {blank.bodies.count} body")

# ---------------------------------------------------------------------------
# Step 2: Compute involute tooth space profile
# ---------------------------------------------------------------------------
ang_pitch = 2 * math.pi / teeth
half_tooth = (math.pi * module_val / 2.0) / pitch_radius
max_roll  = math.sqrt((outer_radius / base_radius) ** 2 - 1)
inv_pitch = math.tan(math.radians(20)) - math.atan(math.tan(math.radians(20)))
N = 15  # spline point count

# Right flank = tooth 0's left flank (mirrored involute)
# Left flank  = tooth 1's right flank
rot_R = -half_tooth - inv_pitch
rot_L = ang_pitch + half_tooth - inv_pitch

pts_R, pts_L = [], []
for j in range(N + 1):
    roll = max_roll * j / N
    ix, iy = involute_xy(base_radius, roll)

    # Right side (mirrored)
    iy_m = -iy
    cr, sr = math.cos(rot_R), math.sin(rot_R)
    pts_R.append(adsk.core.Point3D.create(ix*cr - iy_m*sr, ix*sr + iy_m*cr, 0))

    # Left side
    cl, sl = math.cos(rot_L), math.sin(rot_L)
    pts_L.append(adsk.core.Point3D.create(ix*cl - iy*sl, ix*sl + iy*cl, 0))

# Root circle connection points (same polar angle as involute base points)
V_root_R = adsk.core.Point3D.create(
    root_radius * math.cos(rot_R), root_radius * math.sin(rot_R), 0)
V_root_L = adsk.core.Point3D.create(
    root_radius * math.cos(rot_L), root_radius * math.sin(rot_L), 0)

# ---------------------------------------------------------------------------
# Step 3: Draw ONE tooth space (6-curve closed loop)
# ---------------------------------------------------------------------------
sk2 = rt.sketches.add(rt.xYConstructionPlane)
sk2.name = "Tooth Space"
s = sk2.sketchCurves

# 1: Right radial (root → base)
s.sketchLines.addByTwoPoints(V_root_R, pts_R[0])
# 2: Right involute spline (base → addendum)
s.sketchFittedSplines.add(to_coll(pts_R))
# 3: Addendum arc (short way, connects the two involute tips)
s.sketchArcs.addByCenterStartSweep(center, pts_R[-1], short_sweep(pts_R[-1], pts_L[-1]))
# 4: Left involute spline (addendum → base, reversed)
s.sketchFittedSplines.add(to_coll(list(reversed(pts_L))))
# 5: Left radial (base → root)
s.sketchLines.addByTwoPoints(pts_L[0], V_root_L)
# 6: Root arc (short way, closes the loop at the bottom)
s.sketchArcs.addByCenterStartSweep(center, V_root_L, short_sweep(V_root_L, V_root_R))

# Find the tooth space profile (smallest by area)
prof = None
for i in range(sk2.profiles.count):
    p = sk2.profiles.item(i)
    a = p.areaProperties().area
    if prof is None or a < prof.areaProperties().area:
        prof = p

if prof is None:
    raise RuntimeError("No tooth space profile formed!")

print(f"Tooth space area: {prof.areaProperties().area:.4f} cm^2")

# ---------------------------------------------------------------------------
# Step 4: Extrude cut the tooth space
# ---------------------------------------------------------------------------
ci = extrudes.createInput(prof, adsk.fusion.FeatureOperations.CutFeatureOperation)
ci.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness))
cut = extrudes.add(ci)
cut.name = "Tooth Space"
print(f"Cut OK: {cut.bodies.count} body affected")

# ---------------------------------------------------------------------------
# Step 5: Circular pattern → all teeth
# ---------------------------------------------------------------------------
pc = adsk.core.ObjectCollection.create()
pc.add(cut)
pi = rt.features.circularPatternFeatures.createInput(pc, rt.zConstructionAxis)
pi.quantity = adsk.core.ValueInput.createByReal(teeth)
pi.totalAngle = adsk.core.ValueInput.createByString("360 deg")
pat = rt.features.circularPatternFeatures.add(pi)
pat.name = "Teeth Pattern"
print(f"Patterned {teeth} teeth.")

# ---------------------------------------------------------------------------
# Step 6: Shaft hole
# ---------------------------------------------------------------------------
sk3 = rt.sketches.add(rt.xYConstructionPlane)
sk3.name = "Shaft Hole"
sk3.sketchCurves.sketchCircles.addByCenterRadius(center, shaft_radius)

hi = extrudes.createInput(
    sk3.profiles.item(0),
    adsk.fusion.FeatureOperations.CutFeatureOperation
)
hi.setDistanceExtent(False, adsk.core.ValueInput.createByReal(thickness))
extrudes.add(hi).name = "Shaft Hole"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
print("=" * 50)
print(f"INVOLUTE SPUR GEAR CREATED!")
print(f"  Module: {module_val*10:.0f} mm")
print(f"  Teeth:  {teeth}")
print(f"  OD:     {outer_radius*2:.2f} cm")
print(f"  Root:   {root_radius*2:.2f} cm")
print(f"  Thick:  {thickness:.1f} cm")
print(f"  Shaft:  {shaft_radius*2:.1f} cm dia")
print("=" * 50)
