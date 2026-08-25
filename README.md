# DSA

Research-oriented toolkit for cerebral digital subtraction angiography (DSA) processing in 3D Slicer.

## Initial scope

The first milestone is a reproducible pipeline:

`DICOM DSA -> cine extraction -> preprocessing -> vessel segmentation -> vascular model -> centerlines -> export`

Hemodynamic estimation, multiview reconstruction, vector fields, and CFD are intentionally separated from the initial segmentation milestone.

## Repository structure

- `DSAFlow/` - 3D Slicer scripted module and reusable processing library.
- `scripts/` - standalone utilities for inspection and batch processing.
- `tests/` - automated tests for processing components.
- `docs/` - technical protocol, DICOM metadata, and validation documentation.
- `requirements/` - Slicer extensions and Python dependencies.
- `examples/` - usage examples without patient-identifiable data.

## Data policy

Do not commit clinical DICOM studies, derived patient images, identifiers, or protected health information. Use de-identified local data for development and validation.

## Planned outputs per projection

```text
projection_01/
  vessel_mask.nrrd
  vessel_model.vtp
  centerline.vtp
  metadata.json
```

The metadata record is intended to preserve acquisition geometry and temporal information needed for later multiview and flow analysis.

## Status

Project scaffold initialized. Processing functions are placeholders and will be implemented incrementally with validation at each stage.
