# Feature 22: Dynamic Web Server Port Allocation — Design Document

## Problem

Multiple orchestrator instances running on the same machine all default to port 7070,
causing the second instance to fail binding and its web UI to be unavailable.

## Architecture Overview

Port resolution uses a three-tier priority:

1. **`--web-port N` CLI flag** — ephemeral override; used as-is, no write-back.
2. **`web.port` in `orchestrator-config.yaml`** — stable persisted port; used directly.
3. **No port configured** — auto-scan from `WEB_SERVER_DEFAULT_PORT` (7070) up to
   `WEB_SERVER_PORT_SCAN_MAX` (7170), write the chosen port back to the config file for
   all future runs.

Write-back uses regex text manipulation to preserve existing YAML comments and structure.

## Key Files

| File | Role |
|------|------|
| `langgraph_pipeline/web/server.py` | `find_free_port()`, `write_port_to_config()`, `start_web_server()` |
| `langgraph_pipeline/cli.py` | Three-tier port resolution logic before `start_web_server()` |
| `.claude/orchestrator-config.yaml` | Destination for auto-discovered port write-back |
| `tests/test_web_server.py` | Unit tests for `find_free_port` and `write_port_to_config` |

## Design Decisions

**`find_free_port(start)`** — iterates `range(start, WEB_SERVER_PORT_SCAN_MAX + 1)`,
attempts `socket.bind(('', port))` on each, returns the first that succeeds, raises
`RuntimeError` if none is available.

**`write_port_to_config(port, config_path)`** — reads the file as plain text and applies
one of three regex transformations:
- Update an existing `port:` line inside an existing `web:` section.
- Insert `  port: N` right after the `web:` line when the key is absent.
- Append a new `web:\n  port: N` block when no `web:` section exists.

This avoids round-tripping through a YAML parser (which would drop comments).

**No write-back on `--web-port`** — the CLI flag is ephemeral; only the auto-discovered
value is persisted so the user can override without dirtying the config.

**INFO log on auto-discovery** — when Tier 3 fires, the chosen port and the config file
path are logged at INFO level so the user knows where to point their browser.
