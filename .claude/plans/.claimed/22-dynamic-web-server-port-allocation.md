# Feature 22: Dynamic Web Server Port Allocation

## Problem

When multiple orchestrator instances run on the same machine (different projects), they all
default to port 7070 and collide. The second instance fails to bind and the web UI is unavailable.

## Goal

Allow each project to use its own stable port, auto-detected on first run to avoid conflicts.

## Behaviour

1. **Config-specified port** (`web.port` in `orchestrator-config.yaml`): use it directly, no
   detection needed.

2. **No port configured**: scan for a free port starting from `WEB_SERVER_DEFAULT_PORT` (7070),
   pick the first available one, then write it back to `orchestrator-config.yaml` under `web.port`
   so future invocations use the same port without re-scanning.

3. **Write-back format**: preserve all existing YAML comments and structure; only add/update the
   `web.port` key under the `web:` section (create the section if absent).

## Implementation notes

- Port scan: `socket.bind(('', port))` — increment until successful, cap at e.g. 7170 before
  giving up with a clear error.
- Write-back: use `ruamel.yaml` (already a dependency candidate) or a simple regex/append
  approach to avoid clobbering comments in the config file.
- The port written to config should be logged at INFO level so the user knows where to point
  their browser: `Web server started on port=XXXX (written to orchestrator-config.yaml)`.
- `--web-port` CLI flag still overrides everything; no write-back when the flag is used
  (the flag is ephemeral, not persistent).

## Acceptance criteria

- Two orchestrator instances in different project directories each bind to different ports
  without manual configuration.
- After first auto-detection, `orchestrator-config.yaml` contains `web.port: <N>` and
  subsequent runs use that port without re-scanning.
- `--web-port <N>` overrides the config value for that run only (no write-back).

## LangSmith Trace: c0d4f466-94c7-446d-bbdb-513c86dd7dca
