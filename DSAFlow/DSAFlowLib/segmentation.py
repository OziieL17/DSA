"""Guided cerebral-vessel segmentation routines for 3D Slicer.

Milestone 2 intentionally uses an inspectable threshold workflow rather than a
black-box model. The user previews and adjusts the threshold before accepting.
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
    """Estimate a conservative lower threshold from sampled voxel intensities."""
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


def create_preview(volume_node, lower_threshold, upper_threshold=None, segmentation_node=None):
    """Create/update a threshold-based vascular preview in Segment Editor."""
    if slicer is None:
        raise RuntimeError("Segmentation must run inside 3D Slicer.")
    if upper_threshold is None:
        upper_threshold = scalar_range(volume_node)[1]

    if segmentation_node is None:
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "DSAFlow_Vessels_Preview")
        segmentation_node.CreateDefaultDisplayNodes()
        segmentation_node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)

    segmentation = segmentation_node.GetSegmentation()
    segment_id = segmentation.GetSegmentIdBySegmentName("Vessels")
    if not segment_id:
        segment_id = segmentation.AddEmptySegment("Vessels")

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

    segmentation_node.CreateClosedSurfaceRepresentation()
    return segmentation_node


def remove_preview(segmentation_node):
    if segmentation_node and slicer and segmentation_node.GetScene():
        slicer.mrmlScene.RemoveNode(segmentation_node)
