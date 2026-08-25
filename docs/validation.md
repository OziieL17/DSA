# Validation plan

Validation will be staged rather than treating the final visualization as a single black-box output.

## Segmentation

Candidate metrics: Dice, precision, recall/sensitivity, centerline distance, branch detection, and diameter error against expert reference annotations.

## Centerlines

Evaluate branch topology, endpoint placement, bifurcation correspondence, and spatial centerline error.

## Temporal analysis

Assess repeatability of arrival time, time-to-peak, and temporal-shift estimates under preprocessing variations.

## Multiview reconstruction

Report reprojection error and uncertainty/confidence per reconstructed segment.

## Hemodynamics

Separate measured acquisition quantities, DSA-derived estimates, and CFD-derived quantities in all exports and figures.
