# langgraph_pipeline/shared/dotenv.py
# Minimal .env file loader with no external dependencies.

"""Load environment variables from a .env file.

Supports KEY=value and KEY="value" (with optional quotes).
Lines starting with # are comments. Blank lines are ignored.
Existing environment variables are NOT overwritten.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# Match: optional export, KEY, =, optional quoted value
_LINE_PATTERN = re.compile(
    r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|(.*))\s*$"""
)

DEFAULT_DOTENV_PATH = ".env"


def load_dotenv(path: str = DEFAULT_DOTENV_PATH) -> int:
    """Load variables from a .env file into os.environ.

    Existing environment variables are not overwritten (env takes precedence).

    Args:
        path: Path to the .env file. Defaults to ".env" in the working directory.

    Returns:
        Number of variables loaded.
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
