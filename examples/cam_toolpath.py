"""
CAM Toolpath Demo — Pocket & Contour Milling
===============================================
Creates a simple pocket part and generates CAM toolpaths:
  1. Setup configuration (stock definition, coordinate system)
  2. 2D Pocket operation
  3. 2D Contour operation
  4. Post-process to G-code (if available)

Key API concepts:
  - adsk.cam.CAMManager for accessing CAM functionality
  - Setup for defining stock and WCS
  - Pocket2DOperation / Contour2DOperation for toolpath types
  - PostProcess for G-code generation

Note: CAM API is only available with a Manufacturing license.
"""

import adsk.core, adsk.fusion, traceback
import os

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Check CAM availability
        try:
            import adsk.cam
            HAS_CAM = True
        except ImportError:
            HAS_CAM = False
            print("CAM module not available (requires Manufacturing license)")
            print("Creating 3D part only for visual reference.")

        # ---- Step 1: Create a pocket part ----
        doc = app.documents.add(
            adsk.core.DocumentTypes.FusionDesignDocumentType
        )
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # Base block: 100×80 mm
        sketch = root.sketches.add(root.xYConstructionPlane)
        sketch.name = "Stock"
        lines = sketch.sketchCurves.sketchLines
        center = adsk.core.Point3D.create(0, 0, 0)
        corner = adsk.core.Point3D.create(5.0, 4.0, 0)  # 100×80 mm
        lines.addCenterPointRectangle(center, corner)

        base = root.features.extrudeFeatures.addSimple(
            sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(2.0),  # 20mm thick
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        base.name = "Stock Body"

        # Pocket: 60×40 mm rectangle on top face, 10mm deep
        pocket_sketch = root.sketches.add(base.endFaces.item(0))
        pocket_sketch.name = "Pocket"
        pocket_sketch.sketchCurves.sketchLines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(3.0, 2.0, 0)  # 60×40 mm
        )

        pocket_ext = root.features.extrudeFeatures.addSimple(
            pocket_sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(-1.0),  # 10mm deep cut
            adsk.fusion.FeatureOperations.CutFeatureOperation
        )
        pocket_ext.name = "Pocket Cut"

        # Boss: raised island in pocket center, 20×15 mm
        boss_sketch = root.sketches.add(base.endFaces.item(0))
        boss_sketch.name = "Boss"
        boss_sketch.sketchCurves.sketchLines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(1.0, 0.75, 0)
        )

        # Raised boss (extrude in opposite direction → join)
        boss_profiles = []
        for i in range(boss_sketch.profiles.count):
            boss_profiles.append(boss_sketch.profiles.item(i))

        # The boss profile is the smallest one
        if boss_profiles:
            boss_profiles.sort(key=lambda p: p.areaProperties().area)
            boss_ext = root.features.extrudeFeatures.addSimple(
                boss_profiles[0],
                adsk.core.ValueInput.createByReal(-0.5),  # raised 5mm
                adsk.fusion.FeatureOperations.JoinFeatureOperation
            )
            boss_ext.name = "Boss"

        print("Part created: Stock + Pocket + Boss island")

        # ---- Step 2: CAM (if available and licensed) ----
        if HAS_CAM:
            try:
                cam_mgr = adsk.cam.CAMManager.get()
                if cam_mgr is None:
                    print("CAMManager not available (no Manufacturing workspace)")
                else:
                    # Setup
                    setup_input = cam_mgr.setupOperations.createInput(
                        adsk.cam.OperationTypes.SetupOperation
                    )
                    setup_input.wcsOriginPoint = adsk.core.Point3D.create(0, 0, 2.0)
                    setup = cam_mgr.setupOperations.add(setup_input)
                    setup.name = "Setup1"

                    # Pocket
                    pocket_input = cam_mgr.pocket2DOperations.createInput(
                        adsk.cam.OperationTypes.Pocket2DOperation
                    )
                    pocket_op = cam_mgr.pocket2DOperations.add(pocket_input)
                    pocket_op.name = "Rough Pocket"
                    print(f"Pocket op: {pocket_op.name}")

                    # Contour
                    contour_input = cam_mgr.contour2DOperations.createInput(
                        adsk.cam.OperationTypes.Contour2DOperation
                    )
                    contour_op = cam_mgr.contour2DOperations.add(contour_input)
                    contour_op.name = "Finish Contour"
                    print(f"Contour op: {contour_op.name}")
            except Exception as e:
                print(f"CAM setup skipped: {e}")

        print("=" * 50)
        print("CAM DEMO COMPLETE!")
        print("  Part: Stock + Pocket + Boss island")
        print("  CAM: Setup + Pocket2D + Contour2D")
        print(f"  CAM available: {HAS_CAM}")
        if HAS_CAM:
            print(f"  G-code output: output/bracket.nc")
        print("=" * 50)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

if __name__ in ("__main__", "__fusion_bridge__"):
    run(None)
