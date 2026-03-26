# Design: Dynamic Web Server Port Allocation (Feature 22)

## Problem

When multiple orchestrator instances run on the same machine (different projects), they all
default to port 7070 and collide. The second instance fails to bind and the web UI is unavailable.

## Architecture Overview

Port resolution follows a three-tier priority:

1. `--web-port N` CLI flag: use N directly, no write-back (ephemeral override)
2. `web.port` in `orchestrator-config.yaml`: use it directly, no scan needed
3. Neither: scan for a free port from `WEB_SERVER_DEFAULT_PORT` (7070), pick the first
   available one, write it back to `orchestrator-config.yaml`, then use it on future runs

## Key Files to Modify

### `langgraph_pipeline/web/server.py`

- Add `WEB_SERVER_PORT_SCAN_MAX = 7170` constant (cap for port scan)
- Add `find_free_port(start: int) -> int` — scans `start` to `WEB_SERVER_PORT_SCAN_MAX`
  using `socket.bind(('', port))`, raises `RuntimeError` if none found
- Add `write_port_to_config(port: int, config_path: Path) -> None` — writes `web.port`
  back to `orchestrator-config.yaml` preserving existing YAML comments:
  - If a `web:` section already exists: insert or update `  port: N` under it
  - If no `web:` section exists: append the block at the end of the file
  - Uses plain text regex/append (no new dependencies — avoids adding `ruamel.yaml`)
- Modify `start_web_server()` to accept `config_path: Optional[Path] = None` so
  write-back can locate the config file without coupling to global state

### `langgraph_pipeline/cli.py`

- Update the web-port resolution block (around line 802) to implement the three-tier logic:
  - If `args.web_port`: use it directly (flag overrides, no write-back)
  - Elif `config.get("web", {}).get("port")`: use config value (already persisted, no scan)
  - Else: call `find_free_port(WEB_SERVER_DEFAULT_PORT)`, log at INFO level with port
    and config file path, call `write_port_to_config()`, then start server on that port
- Pass `config_path` to `start_web_server()` for write-back

### `langgraph_pipeline/shared/paths.py`

- Export `ORCHESTRATOR_CONFIG_PATH` (already exists) — used by write-back in `server.py`

## Design Decisions

- **No new dependencies**: `ruamel.yaml` is not in `pyproject.toml`; a regex/append text
  approach avoids adding it. The config file is simple enough for this.
- **Write-back on first run only**: once `web.port` is in the config, subsequent runs
  skip scanning entirely, making startup deterministic.
- **Port scan cap at 7170**: 100 ports gives ample room for typical dev-machine usage.
- **`--web-port` is ephemeral**: no write-back when the CLI flag is used, keeping the
  flag as a one-shot override consistent with the existing `--budget-cap` pattern.
- **INFO log on write-back**: `"Web server started on port=XXXX (written to orchestrator-config.yaml)"`
  so the user knows where to point their browser and that the config was updated.
