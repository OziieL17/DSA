"""DICOM discovery, normalization, and validation for DSAFlow.

Runs inside 3D Slicer and deliberately avoids patient-identifying metadata.
The first milestone recognizes reconstructed 3D-DSA SUB volumes and XA/RF
multiframe cine series, then reports whether each dataset is suitable for the
next processing stage.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional

try:
    import slicer
except ImportError:
    slicer = None


TAGS = {
    "modality": "0008,0060",
    "series_description": "0008,103E",
    "protocol_name": "0018,1030",
    "image_type": "0008,0008",
    "number_of_frames": "0028,0008",
    "rows": "0028,0010",
    "columns": "0028,0011",
    "pixel_spacing": "0028,0030",
    "imager_pixel_spacing": "0018,1164",
    "frame_time_ms": "0018,1063",
    "cine_rate_fps": "0018,0040",
    "primary_angle_deg": "0018,1510",
    "secondary_angle_deg": "0018,1511",
    "sid_mm": "0018,1110",
    "sod_mm": "0018,1111",
    "slice_thickness_mm": "0018,0050",
    "image_position_patient": "0020,0032",
    "image_orientation_patient": "0020,0037",
}


@dataclass
class SeriesReport:
    series_uid: str
    kind: str
    description: str
    file_count: int
    valid: bool
    score: int
    required_ok: List[str]
    warnings: List[str]
    failures: List[str]
    metadata: dict

    def to_dict(self):
        return asdict(self)


def _require_slicer():
    if slicer is None:
        raise RuntimeError("DSAFlow DICOM inspection must run inside 3D Slicer.")
    if slicer.dicomDatabase is None:
        raise RuntimeError("Slicer DICOM database is not available.")


def _value(db, path, tag):
    try:
        value = db.fileValue(path, tag)
        return value if value not in (None, "") else None
    except Exception:
        return None


def _float(value) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int(value) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _split_numbers(value):
    if not value:
        return None
    try:
        return [float(x) for x in value.split("\\")]
    except ValueError:
        return None


def all_series_uids():
    """Return all SeriesInstanceUIDs currently indexed by Slicer's DICOM DB."""
    _require_slicer()
    db = slicer.dicomDatabase
    result = []
    for patient_uid in db.patients():
        for study_uid in db.studiesForPatient(patient_uid):
            result.extend(db.seriesForStudy(study_uid))
    return result


def inspect_series(series_uid: str) -> SeriesReport:
    """Inspect one series without returning PHI.

    Classification:
      * 3D_SUB: reconstructed 3D angiographic subtraction volume
      * XA_CINE: multiframe XA/RF cine acquisition
      * OTHER: not currently accepted by the milestone-1 pipeline
    """
    _require_slicer()
    db = slicer.dicomDatabase
    files = list(db.filesForSeries(series_uid))
    if not files:
        return SeriesReport(series_uid, "OTHER", "", 0, False, 0, [], [], ["Series has no files"], {})

    first = files[0]
    raw = {name: _value(db, first, tag) for name, tag in TAGS.items()}
    modality = raw["modality"] or ""
    image_type = raw["image_type"] or ""
    description = raw["series_description"] or "Unnamed series"

    is_3d_sub = modality == "XA" and "3DANGIO" in image_type and "SUB" in image_type
    is_cine = modality in ("XA", "RF") and _int(raw["number_of_frames"]) is not None
    kind = "3D_SUB" if is_3d_sub else "XA_CINE" if is_cine else "OTHER"

    metadata = {
        "modality": modality,
        "series_description": description,
        "protocol_name": raw["protocol_name"],
        "image_type": image_type,
        "file_count": len(files),
        "number_of_frames": _int(raw["number_of_frames"]),
        "rows": _int(raw["rows"]),
        "columns": _int(raw["columns"]),
        "pixel_spacing_mm": _split_numbers(raw["pixel_spacing"]),
        "imager_pixel_spacing_mm": _split_numbers(raw["imager_pixel_spacing"]),
        "frame_time_ms": _float(raw["frame_time_ms"]),
        "cine_rate_fps": _float(raw["cine_rate_fps"]),
        "primary_angle_deg": _float(raw["primary_angle_deg"]),
        "secondary_angle_deg": _float(raw["secondary_angle_deg"]),
        "sid_mm": _float(raw["sid_mm"]),
        "sod_mm": _float(raw["sod_mm"]),
        "slice_thickness_mm": _float(raw["slice_thickness_mm"]),
        "image_position_patient": _split_numbers(raw["image_position_patient"]),
        "image_orientation_patient": _split_numbers(raw["image_orientation_patient"]),
    }

    ok, warnings, failures = [], [], []

    if kind == "3D_SUB":
        checks = {
            "3D subtraction image type": is_3d_sub,
            "Multiple slices": len(files) >= 50,
            "Pixel spacing": metadata["pixel_spacing_mm"] is not None,
            "Slice thickness": metadata["slice_thickness_mm"] is not None,
            "Patient position": metadata["image_position_patient"] is not None,
            "Patient orientation": metadata["image_orientation_patient"] is not None,
        }
        for label, passed in checks.items():
            (ok if passed else failures).append(label if passed else f"Missing/invalid: {label}")
        spacing = metadata["pixel_spacing_mm"]
        thickness = metadata["slice_thickness_mm"]
        if spacing and thickness and max(abs(spacing[0]-thickness), abs(spacing[1]-thickness)) > 0.02:
            warnings.append("Voxel spacing is not approximately isotropic")

    elif kind == "XA_CINE":
        checks = {
            "Multiframe cine": (metadata["number_of_frames"] or 0) > 1,
            "Frame timing": metadata["frame_time_ms"] is not None or metadata["cine_rate_fps"] is not None,
            "Projection angles": metadata["primary_angle_deg"] is not None and metadata["secondary_angle_deg"] is not None,
            "Source-detector distance": metadata["sid_mm"] is not None,
        }
        for label, passed in checks.items():
            (ok if passed else failures).append(label if passed else f"Missing/invalid: {label}")
        if metadata["imager_pixel_spacing_mm"] is None:
            warnings.append("ImagerPixelSpacing absent: quantitative detector scaling requires review")
        if metadata["sod_mm"] is None:
            warnings.append("Source-to-patient distance absent: patient-plane magnification cannot be directly estimated")
    else:
        failures.append("Series is not a supported 3DANGIO SUB or multiframe XA/RF cine")

    denominator = len(ok) + len(failures)
    score = round(100 * len(ok) / denominator) if denominator else 0
    valid = kind != "OTHER" and len(failures) == 0
    return SeriesReport(series_uid, kind, description, len(files), valid, score, ok, warnings, failures, metadata)


def discover_dsa_series():
    """Return reports for supported or potentially useful angiographic series."""
    reports = [inspect_series(uid) for uid in all_series_uids()]
    return [r for r in reports if r.kind != "OTHER"]


def best_3d_sub_series():
    """Return the highest-scoring reconstructed 3D subtraction series."""
    candidates = [r for r in discover_dsa_series() if r.kind == "3D_SUB"]
    return max(candidates, key=lambda r: (r.valid, r.score, r.file_count), default=None)
