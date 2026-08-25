"""ROI-based multiscale Frangi vesselness and seed connectivity for DSAFlow.

The implementation is intentionally ROI-limited and resampled before Hessian
analysis so it can run inside desktop 3D Slicer without processing the full
512x512x399 reconstruction at native resolution.
"""

try:
    import slicer
    import vtk
except ImportError:
    slicer = None
    vtk = None


def _require_slicer():
    if slicer is None:
        raise RuntimeError("This operation must run inside 3D Slicer.")


def create_centered_roi(volume_node, size_mm=50.0, roi_node=None):
    """Create or reset a cubic Markups ROI centered on the loaded volume."""
    _require_slicer()
    if roi_node is None:
        roi_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsROINode", "DSAFlow_VascularROI")
    bounds = [0.0] * 6
    volume_node.GetRASBounds(bounds)
    center = [(bounds[0]+bounds[1])/2.0, (bounds[2]+bounds[3])/2.0, (bounds[4]+bounds[5])/2.0]
    roi_node.SetCenter(center)
    roi_node.SetSize([float(size_mm)] * 3)
    roi_node.CreateDefaultDisplayNodes()
    roi_node.GetDisplayNode().SetVisibility(True)
    return roi_node


def crop_to_roi(volume_node, roi_node, spacing_scale=2.0, output_node=None):
    """Crop/resample volume to ROI using Slicer's Crop Volume module."""
    _require_slicer()
    if output_node is None:
        output_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "DSAFlow_VascularROI_Volume")
    params = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLCropVolumeParametersNode")
    try:
        params.SetInputVolumeNodeID(volume_node.GetID())
        params.SetROINodeID(roi_node.GetID())
        params.SetOutputVolumeNodeID(output_node.GetID())
        params.SetVoxelBased(True)
        params.SetSpacingScalingConst(float(spacing_scale))
        params.SetInterpolationMode(2)  # linear
        slicer.modules.cropvolume.logic().Apply(params)
    finally:
        slicer.mrmlScene.RemoveNode(params)
    return output_node


def frangi_multiscale(volume_node, sigmas_mm=(0.6, 1.0, 1.6), alpha=0.5, beta=0.5):
    """Compute 3D multiscale Frangi vesselness on a cropped/resampled volume.

    Returns a float32 MRML scalar volume normalized to [0, 1].
    """
    _require_slicer()
    import numpy as np
    from scipy.ndimage import gaussian_filter

    image = slicer.util.arrayFromVolume(volume_node).astype(np.float32, copy=False)
    if image.ndim != 3:
        raise ValueError("Vesselness expects a 3D scalar volume.")
    if image.size > 8_000_000:
        raise RuntimeError(
            f"ROI still contains {image.size:,} voxels. Reduce ROI size or increase ROI resampling before Frangi analysis."
        )

    # Robust normalization limits extreme reconstruction values.
    finite = image[np.isfinite(image)]
    p1, p995 = np.percentile(finite, [1.0, 99.5])
    scale = max(float(p995 - p1), 1e-6)
    norm = np.clip((image - p1) / scale, 0.0, 1.0).astype(np.float32)

    spacing_xyz = volume_node.GetSpacing()
    mean_spacing = float(sum(spacing_xyz) / 3.0)
    best = np.zeros_like(norm, dtype=np.float32)

    for sigma_mm in sigmas_mm:
        sigma = max(float(sigma_mm) / mean_spacing, 0.5)
        s2 = sigma * sigma
        hxx = gaussian_filter(norm, sigma=sigma, order=(0,0,2), mode="nearest") * s2
        hyy = gaussian_filter(norm, sigma=sigma, order=(0,2,0), mode="nearest") * s2
        hzz = gaussian_filter(norm, sigma=sigma, order=(2,0,0), mode="nearest") * s2
        hxy = gaussian_filter(norm, sigma=sigma, order=(0,1,1), mode="nearest") * s2
        hxz = gaussian_filter(norm, sigma=sigma, order=(1,0,1), mode="nearest") * s2
        hyz = gaussian_filter(norm, sigma=sigma, order=(1,1,0), mode="nearest") * s2

        shape = norm.shape
        H = np.empty(shape + (3,3), dtype=np.float32)
        H[...,0,0] = hxx; H[...,1,1] = hyy; H[...,2,2] = hzz
        H[...,0,1] = H[...,1,0] = hxy
        H[...,0,2] = H[...,2,0] = hxz
        H[...,1,2] = H[...,2,1] = hyz
        eig = np.linalg.eigvalsh(H)
        order = np.argsort(np.abs(eig), axis=-1)
        eig = np.take_along_axis(eig, order, axis=-1)
        l1, l2, l3 = eig[...,0], eig[...,1], eig[...,2]

        eps = np.finfo(np.float32).eps
        ra = np.abs(l2) / (np.abs(l3) + eps)
        rb = np.abs(l1) / (np.sqrt(np.abs(l2*l3)) + eps)
        ss = np.sqrt(l1*l1 + l2*l2 + l3*l3)
        c = max(float(np.percentile(ss, 99.5)) * 0.5, 1e-6)
        v = (1.0 - np.exp(-(ra*ra)/(2*alpha*alpha)))
        v *= np.exp(-(rb*rb)/(2*beta*beta))
        v *= (1.0 - np.exp(-(ss*ss)/(2*c*c)))
        # Bright tubular structures on dark background: two dominant Hessian eigenvalues negative.
        v[(l2 > 0) | (l3 > 0)] = 0.0
        best = np.maximum(best, v.astype(np.float32))

    vmax = float(best.max())
    if vmax > 0:
        best /= vmax

    out = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", "DSAFlow_Vesselness")
    out.CopyOrientation(volume_node)
    out.SetOrigin(volume_node.GetOrigin())
    out.SetSpacing(volume_node.GetSpacing())
    slicer.util.updateVolumeFromArray(out, best)
    out.CreateDefaultDisplayNodes()
    out.GetDisplayNode().AutoWindowLevelOff()
    out.GetDisplayNode().SetWindowLevel(1.0, 0.5)
    return out


def create_seed_node(seed_node=None):
    _require_slicer()
    if seed_node is None:
        seed_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "DSAFlow_VesselSeeds")
        seed_node.CreateDefaultDisplayNodes()
    seed_node.GetDisplayNode().SetVisibility(True)
    return seed_node


def seed_connected_mask(vesselness_node, seed_node, threshold=0.12, min_component_voxels=30):
    """Keep only vesselness components intersecting one or more user seeds."""
    _require_slicer()
    import numpy as np
    from scipy import ndimage

    if seed_node is None or seed_node.GetNumberOfControlPoints() == 0:
        raise ValueError("Place at least one seed inside a vessel before seed connectivity.")

    vesselness = slicer.util.arrayFromVolume(vesselness_node)
    binary = np.asarray(vesselness >= float(threshold), dtype=np.uint8)
    labels, n = ndimage.label(binary, structure=ndimage.generate_binary_structure(3, 2))
    if n == 0:
        raise RuntimeError("No connected structures passed the vesselness threshold.")

    ras_to_ijk = vtk.vtkMatrix4x4()
    vesselness_node.GetRASToIJKMatrix(ras_to_ijk)
    selected = set()
    for i in range(seed_node.GetNumberOfControlPoints()):
        ras = [0.0, 0.0, 0.0]
        seed_node.GetNthControlPointPositionWorld(i, ras)
        p = ras_to_ijk.MultiplyPoint([ras[0], ras[1], ras[2], 1.0])
        ii, jj, kk = [int(round(v)) for v in p[:3]]
        if 0 <= kk < labels.shape[0] and 0 <= jj < labels.shape[1] and 0 <= ii < labels.shape[2]:
            lab = int(labels[kk, jj, ii])
            if lab > 0:
                selected.add(lab)

    if not selected:
        raise RuntimeError("Seeds did not intersect the thresholded vesselness mask. Lower vesselness threshold or reposition seeds.")

    counts = np.bincount(labels.ravel())
    selected = {lab for lab in selected if counts[lab] >= int(min_component_voxels)}
    if not selected:
        raise RuntimeError("Seeded components were smaller than the minimum component size.")

    mask = np.isin(labels, list(selected)).astype(np.uint8)
    return mask, {
        "components_total": int(n),
        "seeded_components": len(selected),
        "mask_voxels": int(mask.sum()),
        "threshold": float(threshold),
    }


def mask_to_segmentation(mask, reference_volume, segmentation_node=None):
    """Import a numpy binary mask into a Slicer segmentation."""
    _require_slicer()
    label = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "DSAFlow_SeedConnected_Label")
    label.CopyOrientation(reference_volume)
    label.SetOrigin(reference_volume.GetOrigin())
    label.SetSpacing(reference_volume.GetSpacing())
    slicer.util.updateVolumeFromArray(label, mask.astype("uint8"))
    if segmentation_node is None:
        segmentation_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "DSAFlow_SeedConnectedVessels")
        segmentation_node.CreateDefaultDisplayNodes()
    segmentation_node.GetSegmentation().RemoveAllSegments()
    slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(label, segmentation_node)
    seg = segmentation_node.GetSegmentation()
    ids = vtk.vtkStringArray(); seg.GetSegmentIDs(ids)
    if ids.GetNumberOfValues() > 0:
        seg.GetSegment(ids.GetValue(0)).SetName("SeedConnectedVessels")
    slicer.mrmlScene.RemoveNode(label)
    return segmentation_node
