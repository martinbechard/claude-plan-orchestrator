# langgraph_pipeline/shared/dotenv.py
# Minimal .env file loader with no external dependencies.

"""Load environment variables from .env files.

Loads .env.local first (project-specific overrides, e.g. API keys for the
orchestrator plugin), then .env (the host project's shared defaults).
Since existing variables are never overwritten, .env.local values win
over .env values, and real environment variables win over both.

Supports KEY=value and KEY="value" (with optional quotes).
Lines starting with # are comments. Blank lines are ignored.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# Match: optional export, KEY, =, optional quoted value
_LINE_PATTERN = re.compile(
    r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|(.*))\s*$"""
)

# Load order: .env.local first (higher priority), then .env.
# Since existing vars are never overwritten, first file wins.
DOTENV_FILES = (".env.local", ".env")


def load_dotenv_files() -> int:
    """Load variables from .env.local and .env into os.environ.

    Files are loaded in order: .env.local, then .env. Since existing
    environment variables are never overwritten, the precedence is:
      1. Real environment variables (always win)
      2. .env.local (project-specific, e.g. orchestrator plugin secrets)
      3. .env (host project defaults)

    Returns:
        Total number of variables loaded across all files.
    """
    total = 0
    for path in DOTENV_FILES:
        total += _load_single_file(path)
    return total


def _load_single_file(path: str) -> int:
    """Load variables from a single .env file into os.environ.

    Existing environment variables are not overwritten.

    Args:
        path: Path to the .env file.

    Returns:
        Number of variables loaded from this file.
    """
    if not os.path.isfile(path):
        return 0

    loaded = 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = _LINE_PATTERN.match(line)
                if not match:
                    continue
                key = match.group(1)
                # Value is in one of three capture groups: double-quoted, single-quoted, or unquoted
                value = match.group(2) if match.group(2) is not None else (
                    match.group(3) if match.group(3) is not None else match.group(4).strip()
                )
                if key not in os.environ:
                    os.environ[key] = value
                    loaded += 1
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)

    if loaded:
        logger.info("Loaded %d variable(s) from %s", loaded, path)

    return loaded
