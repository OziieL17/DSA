"""DICOM ingestion and acquisition-metadata extraction.

This module will preserve temporal and projection geometry information required
for later multiview reconstruction and flow estimation.
"""


def inspect_dsa_series(series):
    """Return normalized metadata for a DSA series.

    Implementation pending validation against representative de-identified DICOM.
    """
    raise NotImplementedError
