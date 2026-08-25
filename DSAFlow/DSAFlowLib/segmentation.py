"""Guided cerebral-vessel segmentation routines for 3D Slicer.

Milestone 2 uses an inspectable threshold workflow followed by deterministic
connected-component cleanup. The user can compare raw and clean previews before
accepting, and 3D surface generation is deferred until after cleanup.
"""

try:
    import slicer
    import vtk
except ImportError:
    slicer = None
    vtk = None


def scalar_range(volume_node):
    if volume_node is None or volume_node.GetImageData() is None:
        raise ValueError("A loaded scalar volume is required.")
    return volume_node.GetImageData().GetScalarRange()


def percentile_threshold(volume_node, percentile=99.0, sample_limit=1000000):
    import numpy as np
    array = slicer.util.arrayFromVolume(volume_node).ravel()
    if array.size == 0:
        raise ValueError("Volume contains no voxels.")
    if array.size > sample_limit:
        step = max(1, array.size // sample_limit)
        array = array[::step]
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ValueError("Volume contains no finite intensity values.")
    return float(np.percentile(finite, percentile))


def _ensure_segment(segmentation_node, name):
    segmentation = segmentation_node.GetSegmentation()
    segment_id = segmentation.GetSegmentIdBySegmentName(name)
    if not segment_id:
        segment_id = segmentation.AddEmptySegment(name)
    return segment_id


def create_preview(volume_node, lower_threshold, upper_threshold=None, segmentation_node=None):
    """Create/update a raw 2D threshold preview using Segment Editor."""
    if slicer is None:
        raise RuntimeError("Segmentation must run inside 3D Slicer.")
    if upper_threshold is None:
        upper_threshold = scalar_range(volume_node)[1]

    if segmentation_node is None:
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "DSAFlow_Vessels_Preview")
        segmentation_node.CreateDefaultDisplayNodes()
        segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)

    segmentation_node.RemoveClosedSurfaceRepresentation()
    segment_id = _ensure_segment(segmentation_node, "RawThreshold")

    editor = slicer.qMRMLSegmentEditorWidget()
    editor.setMRMLScene(slicer.mrmlScene)
    parameter_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode")
    editor.setMRMLSegmentEditorNode(parameter_node)
    editor.setSegmentationNode(segmentation_node)
    editor.setSourceVolumeNode(volume_node)
    editor.setCurrentSegmentID(segment_id)

    try:
        editor.setActiveEffectByName("Threshold")
        effect = editor.activeEffect()
        if effect is None:
            raise RuntimeError("Slicer Threshold Segment Editor effect is unavailable.")
        effect.setParameter("MinimumThreshold", str(float(lower_threshold)))
        effect.setParameter("MaximumThreshold", str(float(upper_threshold)))
        effect.self().onApply()
    finally:
        editor.setActiveEffectByName("")
        slicer.mrmlScene.RemoveNode(parameter_node)

    display = segmentation_node.GetDisplayNode()
    if display:
        display.SetVisibility2DFill(True)
        display.SetVisibility2DOutline(True)
        display.SetVisibility3D(False)
        display.SetSegmentVisibility(segment_id, True)

    return segmentation_node


def create_clean_preview(volume_node, lower_threshold, upper_threshold=None,
                         min_component_voxels=100, max_components=40,
                         segmentation_node=None):
    """Create a deterministic connected-component cleaned vessel mask.

    Returns (segmentation_node, statistics_dict).
    Components smaller than ``min_component_voxels`` are removed. Among the
    remaining components, only the largest ``max_components`` are retained.
    """
    if slicer is None:
        raise RuntimeError("Segmentation must run inside 3D Slicer.")

    import numpy as np
    from scipy import ndimage

    source = slicer.util.arrayFromVolume(volume_node)
    if upper_threshold is None:
        upper_threshold = scalar_range(volume_node)[1]

    raw = np.logical_and(source >= float(lower_threshold), source <= float(upper_threshold))
    raw_voxels = int(raw.sum())
    if raw_voxels == 0:
        raise ValueError("Threshold produced an empty mask.")

    structure = ndimage.generate_binary_structure(3, 2)
    labels, component_count = ndimage.label(raw, structure=structure)
    sizes = np.bincount(labels.ravel())
    if sizes.size <= 1:
        raise ValueError("No connected foreground components were found.")

    foreground_sizes = sizes[1:]
    component_ids = np.arange(1, sizes.size)
    eligible = component_ids[foreground_sizes >= int(min_component_voxels)]
    if eligible.size == 0:
        raise ValueError(
            f"No components survived the minimum size of {int(min_component_voxels)} voxels."
        )

    eligible_sizes = sizes[eligible]
    order = eligible[np.argsort(eligible_sizes)[::-1]]
    keep = order[:max(1, int(max_components))]
    clean = np.isin(labels, keep)
    clean_voxels = int(clean.sum())

    if segmentation_node is None:
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "DSAFlow_Vessels_Preview")
        segmentation_node.CreateDefaultDisplayNodes()
        segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)

    segmentation_node.RemoveClosedSurfaceRepresentation()
    segmentation = segmentation_node.GetSegmentation()
    old_clean_id = segmentation.GetSegmentIdBySegmentName("CleanVessels")
    if old_clean_id:
        segmentation.RemoveSegment(old_clean_id)

    labelmap = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "DSAFlow_CleanMask_Temp")
    try:
        slicer.util.updateVolumeFromArray(labelmap, clean.astype(np.uint8))
        ijk_to_ras = vtk.vtkMatrix4x4()
        volume_node.GetIJKToRASMatrix(ijk_to_ras)
        labelmap.SetIJKToRASMatrix(ijk_to_ras)
        labelmap.SetSpacing(volume_node.GetSpacing())
        labelmap.SetOrigin(volume_node.GetOrigin())

        before_ids = set()
        for i in range(segmentation.GetNumberOfSegments()):
            before_ids.add(segmentation.GetNthSegmentID(i))

        slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(labelmap, segmentation_node)

        new_ids = []
        for i in range(segmentation.GetNumberOfSegments()):
            sid = segmentation.GetNthSegmentID(i)
            if sid not in before_ids:
                new_ids.append(sid)
        if not new_ids:
            raise RuntimeError("Could not import cleaned labelmap into segmentation.")
        clean_id = new_ids[-1]
        segmentation.GetSegment(clean_id).SetName("CleanVessels")
    finally:
        slicer.mrmlScene.RemoveNode(labelmap)

    raw_id = segmentation.GetSegmentIdBySegmentName("RawThreshold")
    display = segmentation_node.GetDisplayNode()
    if display:
        display.SetVisibility2DFill(True)
        display.SetVisibility2DOutline(True)
        display.SetVisibility3D(False)
        if raw_id:
            display.SetSegmentVisibility(raw_id, False)
        display.SetSegmentVisibility(clean_id, True)

    stats = {
        "raw_voxels": raw_voxels,
        "clean_voxels": clean_voxels,
        "retained_fraction": clean_voxels / raw_voxels if raw_voxels else 0.0,
        "components_total": int(component_count),
        "components_retained": int(len(keep)),
        "largest_component_voxels": int(sizes[keep[0]]) if len(keep) else 0,
    }
    return segmentation_node, stats


def set_preview_mode(segmentation_node, mode="clean"):
    if segmentation_node is None:
        return
    segmentation = segmentation_node.GetSegmentation()
    display = segmentation_node.GetDisplayNode()
    if not display:
        return
    raw_id = segmentation.GetSegmentIdBySegmentName("RawThreshold")
    clean_id = segmentation.GetSegmentIdBySegmentName("CleanVessels")
    if raw_id:
        display.SetSegmentVisibility(raw_id, mode == "raw")
    if clean_id:
        display.SetSegmentVisibility(clean_id, mode == "clean")


def create_controlled_3d_surface(segmentation_node):
    """Generate 3D only for the cleaned mask and hide the raw segment."""
    if segmentation_node is None:
        raise ValueError("A segmentation node is required.")
    segmentation = segmentation_node.GetSegmentation()
    clean_id = segmentation.GetSegmentIdBySegmentName("CleanVessels")
    if not clean_id:
        raise ValueError("Generate a clean preview before creating a 3D surface.")

    raw_id = segmentation.GetSegmentIdBySegmentName("RawThreshold")
    display = segmentation_node.GetDisplayNode()
    if display and raw_id:
        display.SetSegmentVisibility(raw_id, False)

    segmentation_node.CreateClosedSurfaceRepresentation()
    if display:
        display.SetVisibility3D(True)
        display.SetSegmentVisibility3D(clean_id, True)
        if raw_id:
            display.SetSegmentVisibility3D(raw_id, False)
    return segmentation_node


def remove_preview(segmentation_node):
    if segmentation_node and slicer and segmentation_node.GetScene():
        slicer.mrmlScene.RemoveNode(segmentation_node)
