# Segmentation protocol

## Goal

Produce a reproducible vascular mask and surface model from each DSA projection while retaining the original cine and acquisition metadata locally.

## Required outputs

- `vessel_mask.nrrd`
- `vessel_model.vtp`
- `centerline.vtp`
- `metadata.json`

## Validation principles

- Preserve distal branches when supported by signal.
- Avoid bridging vessels created by projection overlap.
- Record manual corrections.
- Keep preprocessing and segmentation parameters with each result.
- Do not infer unseen vascular continuity solely to improve appearance.
