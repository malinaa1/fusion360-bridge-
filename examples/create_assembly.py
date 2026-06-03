"""
Assembly Demo — Multi-Component Assembly with Joints
======================================================
Creates a simple assembly: base plate + shaft + bushing, joined with
rigid and revolute joints.

Key API concepts:
  - occurrences.addNewComponent() to create sub-components
  - Component isolation for editing
  - AsmJoint for connecting components
  - JointOrigin for defining connection points
"""

import adsk.core, adsk.fusion, traceback
import math

def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        # ---- New document ----
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        root = design.rootComponent

        # ---- Step 1: Create Base Plate (root-level component) ----
        root.name = "Assembly"
        base_sketch = root.sketches.add(root.xYConstructionPlane)
        base_sketch.name = "Base Sketch"
        lines = base_sketch.sketchCurves.sketchLines

        # 80×60 mm rectangle centered at origin
        w, h = 4.0, 3.0  # cm
        lines.addCenterPointRectangle(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Point3D.create(w/2, h/2, 0)
        )

        base_ext = root.features.extrudeFeatures.addSimple(
            base_sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(0.5),  # 5mm thick
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        base_ext.name = "Base Plate"
        print("Base plate created.")

        # ---- Step 2: Create Shaft sub-component ----
        # Create a new occurrence (sub-component)
        shaft_occurrence = root.occurrences.addNewComponent(
            adsk.core.Matrix3D.create()
        )
        shaft_comp = shaft_occurrence.component
        shaft_comp.name = "Shaft"

        # Edit the shaft component to add geometry
        shaft_sketch = shaft_comp.sketches.add(shaft_comp.xZConstructionPlane)
        shaft_sketch.name = "Shaft Profile"
        shaft_sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 0.5  # 10mm dia
        )

        shaft_ext = shaft_comp.features.extrudeFeatures.addSimple(
            shaft_sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(4.0),  # 40mm long
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        shaft_ext.name = "Shaft Body"
        print("Shaft component created.")

        # ---- Step 3: Position the shaft on the base ----
        # Create a joint origin on the shaft (bottom center)
        shaft_origin_input = shaft_comp.jointOrigins.createInput(
            shaft_comp.bRepBodies.item(0).faces.item(0)  # end face
        )
        shaft_origin = shaft_comp.jointOrigins.add(shaft_origin_input)

        # Position shaft relative to root using a rigid joint
        # Move shaft to (2, 0, 0.25) — half of base thickness
        shaft_transform = adsk.core.Matrix3D.create()
        shaft_transform.translation = adsk.core.Vector3D.create(2.0, 0, 0.5)
        shaft_occurrence.transform = shaft_transform
        print("Shaft positioned.")

        # ---- Step 4: Create Bushing sub-component ----
        bushing_occurrence = root.occurrences.addNewComponent(
            adsk.core.Matrix3D.create()
        )
        bushing_comp = bushing_occurrence.component
        bushing_comp.name = "Bushing"

        # Outer circle
        b_sketch = bushing_comp.sketches.add(bushing_comp.xYConstructionPlane)
        b_sketch.sketchCurves.sketchCircles.addByCenterRadius(
            adsk.core.Point3D.create(0, 0, 0), 0.8  # 16mm OD
        )
        bushing_ext = bushing_comp.features.extrudeFeatures.addSimple(
            b_sketch.profiles.item(0),
            adsk.core.ValueInput.createByReal(1.5),  # 15mm thick
            adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        )
        bushing_ext.name = "Bushing Body"
        print("Bushing component created.")

        # ---- Step 5: Create revolute joint between shaft and bushing ----
        # Get planar faces for joint origins
        shaft_face = shaft_comp.bRepBodies.item(0).faces.item(2)  # cylindrical face
        bushing_face = bushing_comp.bRepBodies.item(0).faces.item(2)

        # Create joint origins
        so = shaft_comp.jointOrigins.createInput(shaft_face)
        shaft_joint_origin = shaft_comp.jointOrigins.add(so)

        bo = bushing_comp.jointOrigins.createInput(bushing_face)
        bushing_joint_origin = bushing_comp.jointOrigins.add(bo)

        # Create revolute joint input
        joint_input = root.asmJoints.createInput(
            shaft_occurrence, shaft_joint_origin,  # component 1 + origin
            bushing_occurrence, bushing_joint_origin  # component 2 + origin
        )
        joint_input.isFlipped = False
        joint_input.jointMotionType = adsk.fusion.JointTypes.RevoluteJointType

        revolute_joint = root.asmJoints.add(joint_input)
        revolute_joint.name = "Shaft-Bushing Revolute"
        print("Revolute joint created.")

        # ---- Done ----
        print("=" * 50)
        print("ASSEMBLY COMPLETE!")
        print("  Components: Base Plate + Shaft + Bushing")
        print("  Joints: 1 Revolute")
        print("=" * 50)

    except:
        if ui:
            ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))
