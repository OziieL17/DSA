# DSAFlow pipeline

## Milestone 1 — reproducible vascular segmentation

1. Import DICOM DSA.
2. Inspect cine frames and acquisition metadata.
3. Preprocess the temporal image stack.
4. Generate a maximum-opacification representation when appropriate.
5. Segment the vascular tree.
6. Convert the segmentation to a vascular surface model.
7. Extract centerlines.
8. Run quality control.
9. Export mask, model, centerline, and metadata.

## Milestone 2 — temporal flow

- Time-density curves along centerlines.
- Contrast arrival time and time-to-peak.
- Centerline contrast-propagation velocity.
- Confidence estimates.

## Milestone 3 — multiview geometry

- Projection calibration.
- Cross-view vascular correspondence.
- 3D reconstruction with reprojection error.

## Milestone 4 — hemodynamic visualization

- Velocity scalar maps.
- Direction vectors and streamlines.
- Relative flow estimates.

## Milestone 5 — CFD research

Pressure, wall shear stress, oscillatory shear index, and other CFD-derived quantities require a separately validated computational model and must not be presented as direct DSA measurements.
