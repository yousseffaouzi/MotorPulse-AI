"""Local-only CWRU seeded-bearing-fault inspection (MP-031).

The adapter reads a deliberately small MATLAB-v5 subset using only the Python
standard library.  It never downloads data, infers labels from filenames, or
emits raw samples.  User-supplied metadata identifies the exact channel and
seeded test condition; unsupported MAT structures fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isfinite, sqrt
from pathlib import Path
import struct
import zlib

from .ims import _read_strict_json, write_local_manifest

SOURCE_CARD_ID = "cwru-bearing-data-center"
OFFICIAL_SOURCE_URL = "https://engineering.case.edu/bearingdatacenter"
MAX_MAT_BYTES = 32 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_VARIABLES = 256
MAX_VECTOR_SAMPLES = 1_000_000
MAX_ELEMENT_BYTES = 64 * 1024 * 1024

MI_INT8 = 1
MI_INT32 = 5
MI_UINT32 = 6
MI_DOUBLE = 9
MI_MATRIX = 14
MI_COMPRESSED = 15
MX_DOUBLE_CLASS = 6
MX_COMPLEX = 0x0800

_METADATA_KEYS = frozenset(
    (
        "metadata_version",
        "source_url",
        "file_name",
        "channel_variable",
        "bearing_location",
        "fault_type",
        "fault_diameter_mils",
        "outer_race_position",
        "load_hp",
        "sample_rate_hz",
        "value_unit",
    )
)
_FAULT_TYPES = frozenset(("normal", "inner_race", "ball", "outer_race"))
_FAULT_DIAMETERS = frozenset((7, 14, 21, 28, 40))
_OUTER_POSITIONS = frozenset(("3_oclock", "6_oclock", "12_oclock"))
_BEARING_LOCATIONS = frozenset(("drive_end", "fan_end"))
_SAMPLE_RATES = frozenset((12000, 48000))


def _read_metadata(path: str | Path, source: Path) -> dict:
    document = _read_strict_json(path, 16 * 1024)
    if type(document) is not dict or set(document) != _METADATA_KEYS:
        raise ValueError("CWRU metadata keys differ from the v1 contract")
    if document["metadata_version"] != "1.0.0":
        raise ValueError("unsupported CWRU metadata_version")
    if document["source_url"] != OFFICIAL_SOURCE_URL:
        raise ValueError("source_url must be the official CWRU Bearing Data Center")
    if document["file_name"] != source.name:
        raise ValueError("metadata file_name does not match local MAT filename")
    channel = document["channel_variable"]
    if type(channel) is not str or not 1 <= len(channel) <= 128 or not channel.isascii():
        raise ValueError("channel_variable must be 1-128 ASCII characters")
    location = document["bearing_location"]
    if location not in _BEARING_LOCATIONS:
        raise ValueError("bearing_location must be drive_end or fan_end")
    fault = document["fault_type"]
    if fault not in _FAULT_TYPES:
        raise ValueError("unsupported CWRU seeded fault_type")
    diameter = document["fault_diameter_mils"]
    if fault == "normal":
        if diameter is not None:
            raise ValueError("normal baseline must not declare a fault diameter")
    elif type(diameter) is not int or diameter not in _FAULT_DIAMETERS:
        raise ValueError("seeded faults require a documented CWRU fault diameter")
    position = document["outer_race_position"]
    if fault == "outer_race":
        if position not in _OUTER_POSITIONS:
            raise ValueError("outer-race faults require 3/6/12 o'clock position metadata")
    elif position is not None:
        raise ValueError("outer_race_position applies only to outer-race faults")
    load = document["load_hp"]
    if type(load) is not int or not 0 <= load <= 3:
        raise ValueError("load_hp must be an integer from 0 through 3")
    rate = document["sample_rate_hz"]
    if type(rate) is not int or rate not in _SAMPLE_RATES:
        raise ValueError("sample_rate_hz must be 12000 or 48000")
    if rate == 48000 and location != "drive_end":
        raise ValueError("48 kHz is documented only for drive-end CWRU experiments")
    if document["value_unit"] != "unknown":
        raise ValueError("value_unit must remain unknown unless separately verified")
    return document


def _mat_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("CWRU input must be a regular, non-symlink MAT file")
    size = path.stat(follow_symlinks=False).st_size
    if not 128 <= size <= MAX_MAT_BYTES:
        raise ValueError(f"MAT file must be 128-{MAX_MAT_BYTES} bytes")
    data = path.read_bytes()
    if len(data) != size:
        raise ValueError("MAT file changed while being read")
    return data


def _element(data: bytes, offset: int, endian: str) -> tuple[int, bytes, int]:
    if offset < 0 or offset + 8 > len(data):
        raise ValueError("truncated MATLAB data element tag")
    first, second = struct.unpack_from(endian + "II", data, offset)
    small_size = first >> 16
    small_type = first & 0xFFFF
    if small_size:
        if not 1 <= small_size <= 4:
            raise ValueError("invalid small MATLAB data element")
        return small_type, data[offset + 4 : offset + 4 + small_size], offset + 8
    kind, size = first, second
    if size > MAX_ELEMENT_BYTES:
        raise ValueError("MATLAB data element exceeds configured size limit")
    start = offset + 8
    end = start + size
    if end > len(data):
        raise ValueError("truncated MATLAB data element")
    padded = end + ((-size) % 8)
    if padded > len(data):
        raise ValueError("truncated MATLAB data element padding")
    return kind, data[start:end], padded


def _uncompress(payload: bytes) -> bytes:
    decoder = zlib.decompressobj()
    try:
        data = decoder.decompress(payload, MAX_DECOMPRESSED_BYTES + 1)
    except zlib.error as exc:
        raise ValueError("invalid compressed MATLAB element") from exc
    if len(data) > MAX_DECOMPRESSED_BYTES or decoder.unconsumed_tail or not decoder.eof:
        raise ValueError("compressed MATLAB element exceeds limit or is incomplete")
    tail = decoder.flush()
    if tail:
        if len(data) + len(tail) > MAX_DECOMPRESSED_BYTES:
            raise ValueError("decompressed MATLAB element exceeds configured limit")
        data += tail
    if decoder.unused_data:
        raise ValueError("compressed MATLAB element has trailing data")
    return data


def _matrix_vector(payload: bytes, target: str, endian: str) -> tuple[str, bytes, int] | None:
    offset = 0
    flags: int | None = None
    dims: tuple[int, ...] | None = None
    name: str | None = None
    real: bytes | None = None
    real_kind: int | None = None
    while offset < len(payload):
        kind, part, offset = _element(payload, offset, endian)
        if flags is None and kind == MI_UINT32:
            if len(part) < 8:
                raise ValueError("invalid MATLAB array flags")
            flags = struct.unpack_from(endian + "I", part, 0)[0]
        elif dims is None and kind == MI_INT32:
            if not part or len(part) % 4:
                raise ValueError("invalid MATLAB dimensions")
            dims = struct.unpack(endian + "i" * (len(part) // 4), part)
        elif name is None and kind == MI_INT8:
            try:
                name = part.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError("MATLAB variable name must be ASCII") from exc
        elif real is None and kind in (MI_DOUBLE,):
            real_kind = kind
            real = part
    if name != target:
        return None
    if flags is None or dims is None or real is None or real_kind is None:
        raise ValueError("target MATLAB matrix is missing required fields")
    if (flags & 0xFF) != MX_DOUBLE_CLASS or flags & MX_COMPLEX:
        raise ValueError("target MATLAB variable must be a real double array")
    if len(dims) < 2 or any(value < 1 for value in dims):
        raise ValueError("target MATLAB variable has invalid dimensions")
    non_singleton = [value for value in dims if value != 1]
    if len(non_singleton) > 1:
        raise ValueError("target MATLAB variable must be a vector")
    samples = 1
    for value in dims:
        samples *= value
        if samples > MAX_VECTOR_SAMPLES:
            raise ValueError("target MATLAB vector exceeds sample limit")
    if len(real) != samples * 8:
        raise ValueError("target MATLAB vector byte count does not match dimensions")
    return name, real, samples


def _extract_vector(data: bytes, target: str) -> tuple[bytes, int, str]:
    if len(data) < 128 or not data[:116].startswith(b"MATLAB 5.0 MAT-file"):
        raise ValueError("only MATLAB v5 MAT files are supported")
    marker = data[126:128]
    if marker == b"IM":
        endian = "<"
    elif marker == b"MI":
        endian = ">"
    else:
        raise ValueError("invalid MATLAB endian marker")
    offset = 128
    found: tuple[bytes, int] | None = None
    variables = 0
    while offset < len(data):
        kind, payload, offset = _element(data, offset, endian)
        nested = payload
        if kind == MI_COMPRESSED:
            nested = _uncompress(payload)
            nested_offset = 0
            while nested_offset < len(nested):
                nested_kind, nested_payload, nested_offset = _element(
                    nested, nested_offset, endian
                )
                if nested_kind != MI_MATRIX:
                    raise ValueError("compressed MATLAB payload contains unsupported element")
                variables += 1
                if variables > MAX_VARIABLES:
                    raise ValueError("too many MATLAB variables")
                result = _matrix_vector(nested_payload, target, endian)
                if result is not None:
                    if found is not None:
                        raise ValueError("duplicate target MATLAB variable")
                    _, real, samples = result
                    found = (real, samples)
        elif kind == MI_MATRIX:
            variables += 1
            if variables > MAX_VARIABLES:
                raise ValueError("too many MATLAB variables")
            result = _matrix_vector(nested, target, endian)
            if result is not None:
                if found is not None:
                    raise ValueError("duplicate target MATLAB variable")
                _, real, samples = result
                found = (real, samples)
        else:
            raise ValueError("unsupported top-level MATLAB data element")
    if found is None:
        raise ValueError(f"channel_variable not found in MAT file: {target}")
    return found[0], found[1], endian


def _summary(real: bytes, samples: int, endian: str) -> dict:
    total = 0.0
    squares = 0.0
    low = float("inf")
    high = float("-inf")
    peak = 0.0
    count = 0
    for (value,) in struct.iter_unpack(endian + "d", real):
        if not isfinite(value):
            raise ValueError("target MATLAB vector contains a non-finite value")
        count += 1
        total += value
        squares += value * value
        if not isfinite(total) or not isfinite(squares):
            raise ValueError("target MATLAB vector overflows summary arithmetic")
        low = min(low, value)
        high = max(high, value)
        peak = max(peak, abs(value))
    if count != samples or count < 1:
        raise ValueError("target MATLAB vector sample count mismatch")
    rms = sqrt(squares / count)
    return {
        "sample_count": count,
        "mean_native": total / count,
        "rms_native": rms,
        "peak_to_peak_native": high - low,
        "crest_factor": peak / rms if rms else 0.0,
    }


def inspect_cwru_file(input_mat: str | Path, metadata_json: str | Path) -> dict:
    """Inspect one user-supplied CWRU MAT file without exposing its samples."""
    source = Path(input_mat)
    metadata = _read_metadata(metadata_json, source)
    data = _mat_bytes(source)
    real, samples, endian = _extract_vector(data, metadata["channel_variable"])
    summary = _summary(real, samples, endian)
    rate = metadata["sample_rate_hz"]
    summary.update(
        {
            "sample_rate_hz": rate,
            "window_duration_s": samples / rate,
            "value_unit": metadata["value_unit"],
        }
    )
    fault = metadata["fault_type"]
    return {
        "report_version": "1.0.0",
        "source_card_id": SOURCE_CARD_ID,
        "source_file_name": source.name,
        "source_file_bytes": len(data),
        "source_file_sha256": hashlib.sha256(data).hexdigest(),
        "metadata": {
            **metadata,
            "experiment_type": "seeded_fault_not_run_to_failure",
            "fault_method": "EDM" if fault != "normal" else None,
        },
        "series": summary,
        "labels": {
            "seeded_fault_type": fault,
            "seeded_fault_diameter_mils": metadata["fault_diameter_mils"],
            "run_to_failure": False,
            "failure_time": None,
            "failure_probability": None,
            "remaining_useful_life": None,
        },
        "rights": {
            "official_source": OFFICIAL_SOURCE_URL,
            "rights_status": "unverified_for_redistribution",
            "publication_status": "local_only_do_not_redistribute",
            "raw_or_derived_data_in_repository": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect one user-supplied local CWRU MATLAB-v5 bearing file; "
            "no download or redistribution"
        )
    )
    parser.add_argument("--input", type=Path, required=True, help="local CWRU .mat file")
    parser.add_argument(
        "--metadata",
        type=Path,
        required=True,
        help="explicit local CWRU metadata JSON; labels are never inferred from filename",
    )
    parser.add_argument("--out", type=Path, required=True, help="new summary JSON; no overwrite")
    args = parser.parse_args()
    try:
        report = inspect_cwru_file(args.input, args.metadata)
        write_local_manifest(args.out, report)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(
        f"Inspected local CWRU seeded-fault file: {report['source_file_name']} "
        f"({report['series']['sample_count']} samples; summary only)"
    )


if __name__ == "__main__":
    main()
