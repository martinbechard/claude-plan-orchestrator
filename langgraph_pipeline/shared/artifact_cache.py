# langgraph_pipeline/shared/artifact_cache.py
# Sidecar-metadata-based artifact freshness cache using SHA-256 content hashing.
# Design: docs/plans/2026-04-02-86-idempotent-intake-with-staleness-check-design.md

"""Artifact cache: records input hashes when outputs are produced and checks freshness.

The cache mirrors make-style dependency tracking.  Each pipeline step declares its
input files and output name; this module stores a content fingerprint in a per-workspace
sidecar (.artifact-meta.json) at production time and recomputes fingerprints at
restart time to decide whether the step can be skipped.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

# ─── Constants ────────────────────────────────────────────────────────────────

SIDECAR_FILENAME = ".artifact-meta.json"
HASH_ALGORITHM = "sha256"
READ_CHUNK_SIZE = 65536  # 64 KiB – balances memory use and syscall overhead

logger = logging.getLogger(__name__)


# ─── Types ────────────────────────────────────────────────────────────────────

# Internal sidecar format:
# {
#   "<output_name>": {
#     "<input_path>": "<sha256-hex>",
#     ...
#     "timestamp": "<ISO 8601>"
#   }
# }
#
# Using plain dict[str, str] for the per-entry values avoids a TypedDict that
# would need Union[str, dict] for the timestamp key — simpler and correct here.

SidecarEntry = dict[str, str]
SidecarData = dict[str, SidecarEntry]


# ─── Public API ───────────────────────────────────────────────────────────────


def record_artifact(
    workspace_dir: Union[str, Path],
    output_name: str,
    input_paths: list[Union[str, Path]],
) -> None:
    """Record the SHA-256 content hashes of *input_paths* for *output_name*.

    Writes (or updates) an entry in ``workspace_dir/.artifact-meta.json``
    mapping *output_name* to a dict of ``{input_path: sha256_hex, ...,
    "timestamp": ISO8601}``.  The sidecar file is created if it does not exist.

    Missing input files are skipped with a warning rather than raising so that
    a partially completed step can still record whatever it produced.
    """
    workspace = Path(workspace_dir)
    sidecar_path = workspace / SIDECAR_FILENAME

    sidecar = _read_sidecar(sidecar_path)

    entry: SidecarEntry = {}
    for raw_path in input_paths:
        path = Path(raw_path)
        if not path.exists():
            logger.warning(
                "record_artifact: input file does not exist, skipping: %s", path
            )
            continue
        entry[str(path)] = _sha256(path)

    entry["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
    sidecar[output_name] = entry

    _write_sidecar(sidecar_path, sidecar)


def is_artifact_fresh(
    workspace_dir: Union[str, Path],
    output_name: str,
    input_paths: list[Union[str, Path]],
) -> bool:
    """Return True if the named artifact is still valid for the given inputs.

    Three conditions must all hold:
    1. The output file (``workspace_dir/output_name``) exists.
    2. The sidecar file contains an entry for *output_name*.
    3. The current SHA-256 hash of every path in *input_paths* matches the
       stored hash for that path.

    Returns False (and logs a debug message) on any mismatch or missing file.
    """
    workspace = Path(workspace_dir)
    output_path = workspace / output_name

    if not output_path.exists():
        logger.debug("is_artifact_fresh: output file missing: %s", output_path)
        return False

    sidecar_path = workspace / SIDECAR_FILENAME
    sidecar = _read_sidecar(sidecar_path)

    if output_name not in sidecar:
        logger.debug(
            "is_artifact_fresh: no sidecar entry for output '%s'", output_name
        )
        return False

    stored_entry = sidecar[output_name]

    for raw_path in input_paths:
        path = Path(raw_path)
        path_key = str(path)

        if path_key not in stored_entry:
            logger.debug(
                "is_artifact_fresh: no stored hash for input '%s' in entry '%s'",
                path_key,
                output_name,
            )
            return False

        if not path.exists():
            logger.debug(
                "is_artifact_fresh: input file missing: %s", path
            )
            return False

        current_hash = _sha256(path)
        if current_hash != stored_entry[path_key]:
            logger.debug(
                "is_artifact_fresh: hash mismatch for '%s' (stored=%s, current=%s)",
                path_key,
                stored_entry[path_key][:8],
                current_hash[:8],
            )
            return False

    return True


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    """Compute and return the SHA-256 hex digest of the file at *path*."""
    digest = hashlib.new(HASH_ALGORITHM)
    with open(path, "rb") as fh:
        while chunk := fh.read(READ_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _read_sidecar(sidecar_path: Path) -> SidecarData:
    """Load the sidecar JSON, returning an empty dict on any error or absence."""
    if not sidecar_path.exists():
        return {}
    try:
        with open(sidecar_path) as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data  # type: ignore[return-value]
        logger.warning("Sidecar %s is not a dict; resetting", sidecar_path)
        return {}
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to read sidecar %s: %s", sidecar_path, exc)
        return {}


def _write_sidecar(sidecar_path: Path, data: SidecarData) -> None:
    """Persist *data* to *sidecar_path*, creating parent dirs as needed."""
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(sidecar_path, "w") as fh:
            json.dump(data, fh, indent=2)
    except IOError as exc:
        logger.warning("Failed to write sidecar %s: %s", sidecar_path, exc)
