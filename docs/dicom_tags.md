# DICOM metadata inventory

The exact tag set will be determined from representative de-identified angiography studies.

Candidate metadata groups to preserve:

- Study/series/SOP identifiers after de-identification.
- Rows, columns, bit depth, photometric interpretation.
- Pixel spacing / imager pixel spacing when available.
- Number of frames and frame timing.
- Frame time or frame-time vector.
- Positioner primary and secondary angles.
- Source-to-detector and source-to-patient distances when available.
- Acquisition time and temporal ordering.
- Vendor/private geometry tags only after explicit documentation and validation.

No patient-identifying fields should be exported into research metadata.
