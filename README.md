# Aether Engine

A local-first command-line tool for tracking project tasks and recording a searchable event history. By default, data is stored in `.aether-engine.sqlite3` at the nearest parent directory containing `pyproject.toml`; outside a project, it is stored in the current directory. Each project therefore gets its own database.

## Install and test

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,api,secure-vault,spin-network-visualization]"
python -m pytest
```

On Windows, activate with `.venv\Scripts\activate` instead.

The editable install exposes the `aether-engine` command from this checkout. The development, API, secure-vault, and spin-network-visualization extras install the dependencies needed by the full test suite. After code changes, rerun `python -m pytest`; to verify the installed command, run `aether-engine --help`.

## Build a standalone executable

Install the optional build dependency with `python -m pip install -e ".[build]"`, then run `python build_app.py`. PyInstaller writes the executable to `dist/`; the build targets the operating system and architecture of the Python interpreter used to run the script. Check the result with `./dist/aether-engine --help` on macOS and Linux.

To copy the current engine source, tests, and project configuration into another directory without overwriting existing files, run `python seed_project.py --target ../new-aether-project`.

The optional `aether_engine.ai_bridge.AetherLunaBridge` runs in offline simulation mode by default; try it with `python -m aether_engine.ai_bridge`. It does not send requests to OpenAI, and its default `gpt-6-luna` identifier is a caller-provided label, not a verified available model. Live provider integration requires an explicitly supplied transport callable and API key; no OpenAI SDK or live provider adapter is included.

`aether_engine.ai_bridge.LocalAirGappedEngine` can run text inference with a local Qwen 2.5 Coder GGUF file. Install the optional backend with `python -m pip install -e ".[local-ai]"`, then place `qwen2.5-coder-7b-q4.gguf` in the project `models/` directory, or set `AETHER_MODEL_PATH` to an existing GGUF file. The engine loads the model on first inference and makes no network requests; vision inference is not supported by this text model.

The local REST API is available with `python -m pip install -e ".[api]"`. Run the full API with `uvicorn app:app --reload` during development or `aether-server` for the packaged entry point. Both listen on `127.0.0.1:8000` by default; all routes reject non-loopback clients, including if Uvicorn is configured to bind a public interface. Set `AETHER_DATABASE_PATH` to select the SQLite database; otherwise the API uses the nearest project `.aether-engine.sqlite3`. Interactive OpenAPI docs are at `/docs`.

### Copernicus companion shell

For the independent **Copernicus** shell, run
`python historian_matrix.py` and open `http://127.0.0.1:8765/`.
Install the existing API dependencies (`python -m pip install -e ".[api]"`) if
needed. The shell has Copernicus, Weather, and Stargazer tabs. Copernicus is
the warm, personalized local chat companion; history capture and search are
not part of this shell. Use `--port` to choose another port.
The launcher does not import master-matrix engines, start simulated test drives,
expose export/restore operations, or read matrix telemetry.
It is loopback-only, for the local OS user, not a multi-user commercial service.
AI is disabled by default. To enable local AI, run
`python historian_matrix.py --ollama-model atlas-qwen-coder:latest`.
This model alias was approved by the owner as isolated from proprietary data.
Ollama must serve it at `http://localhost:11434`. Chat sends the current typed
message and, when available, the latest cloud-cover reading from the weather
panel; saved entries and previous chat messages are not sent. Replies are not
saved automatically and disappear on reload. Copernicus has no persistent
profile or memory and has no technical connection to Matrix data or controls.
Requests are serialized, have
a 120-second backend timeout, and report failures without affecting shell navigation.
The health route reports AI configuration, not verified model availability.
The non-disclosure instruction is a behavioral prompt, not a guaranteed
formula/content filter; keep the model isolated and do not paste proprietary
material into chat. This is still a local evaluation interface, not certified
for commercial disclosure prevention. Edit `frontend/copernicus.js` for chat
interactions and `historian_matrix.py` for the independent shell routes.

Copernicus uses Matrix-inspired branding, ember-and-gold shell styling, and a
warm, attentive, practical companion voice. This is a public identity/style
affiliation only: no internal prompts, Matrix reasoning, algorithms, telemetry,
or control interfaces are supplied to the assistant. The independent shell's
theme is scoped to `data-copernicus="true"` so the separate weather shell keeps
its automatic light/dark appearance. The stargazer retains its dark sky canvas.

Install the numerical and atomic-engine dependencies with
`python -m pip install -e ".[command-center]"`, run `python aether_master_matrix.py`,
and open `http://127.0.0.1:8000/`. The standalone dashboard binds only to
loopback. Set `AETHER_PORT` to select another port. At startup it runs a
30-step simulated collapse test drive and records entropy and action metrics
to `historian_telemetry_vault.json` beside the launcher. Set
`AETHER_HISTORIAN_LOG_FILE` to select another log path. Telemetry values are
simulated, not physical measurements. The Copernicus tab uses local Ollama via
`AETHER_OLLAMA_MODEL` (default `qwen2.5-coder`); the current message and latest
cloud-cover reading may be sent, and chat is not persisted or connected to
Matrix telemetry. No affiliation with or endorsement by Open-Meteo is implied.
Ollama must serve the configured model at `http://localhost:11434`.

The dashboard embeds the Copernicus, Weather, and Stargazer shell at `/weather`
on the same server; no second server or frontend dependencies are required.
Switch views using the **Copernicus**, **Weather**, and **Stargazer** tabs. Keyboard users can
switch tabs with Left/Right arrows, Home, or End. The stargazer loads on its first
selection, retains its controls and view when switching back, and pauses its
animation while its tab is hidden. Weather readings and city selection also
remain intact across tab changes. Weather and sky data are not linked.
The weather view provides
city search, current temperature in Fahrenheit, wind in mph, humidity, cloud
cover, and a five-day forecast through Open-Meteo, refreshing every five minutes.
The latest cloud-cover reading, city, observation time, timezone, and live/stale
status can be included as context when chatting with Copernicus. The browser
sends only the city search and weather coordinates to the two weather APIs;
the weather routes do not read matrix telemetry or invoke internal models.
Internet access is required for live weather. Failed requests visibly report
the error and retain the last successful readings as **OFFLINE / STALE** for
their original city. Before any successful request, readings remain unavailable;
no fictional fallback values are presented. Retained readings last only until
the page is reloaded.

Update markup in `frontend/weather.html`, styling in `frontend/weather.css`,
and API endpoints, refresh interval, timeout, and default city in
`frontend/weather.js`. If API origins change, update the weather route's
`connect-src` policy in `aether_master_matrix.py` too. Reload the page after asset
changes; restart the server after Python changes. The default public API setup
is for evaluation: verify Open-Meteo's current commercial licensing, limits,
and attribution requirements before offering this as a paid product.

The included Stargazer at `/stargazer` is embedded in the shell's Stargazer tab
and remains available as a standalone page.
It renders an **illustrative**, not astronomically positioned, starfield with
Orion, the Big Dipper asterism, and Cassiopeia. Drag with a mouse or touch,
use arrow keys on the focused canvas, or choose stars from the accessible guide.
Controls toggle constellation lines and visual drift, spawn simulated meteors,
and reset the view. Reduced-motion preferences disable automatic drift and
twinkling by default; manually requested effects remain available. Animation
pauses when the page is hidden.

The UTC clock uses the device clock. Moon phase, cloud cover, and ISS coordinates
are explicitly **Not connected in Stargazer**; its illustrative sky is separate
from the live cloud-cover reading in Weather. No orbital measurements are
fabricated, and this page makes no network requests or reads of private
telemetry. Edit `frontend/stargazer.html`,
`frontend/stargazer.css`, and `frontend/stargazer.js` to maintain the shell.

The Stargazer includes an Ollama comms panel when served by
`historian_matrix.py --ollama-model atlas-qwen-coder:latest`. It reuses the
approved `/api/chat` backend rather than connecting the browser directly to
Ollama or weakening CORS. Only the current message is relayed; replies are
rendered as text, and neither chat nor clock references are saved to history.
The panel samples `/api/clock` every minute, displays an approximate backend UTC
clock, and labels exchanges with exact backend request/response timestamps.
Historian receives the request timestamp as a system communication reference.
This does not synchronize devices, connect to Matrix, or guarantee a model
acknowledgment. The Stargazer panel sends only its current typed message, without
the Weather tab's cloud-cover context. On the separate master-matrix server, the
panel explicitly reports that the comms backend is unavailable.

This standalone launcher replaces the former FastAPI command-center dashboard;
it no longer serves the task, event, diagnostics, backup, or local AI API routes.
Use the separately documented `aether-server` or `uvicorn app:app` command for
the Aether Engine REST API.

The API exposes `GET /health`, `GET|POST /api/v1/tasks`, `PATCH /api/v1/tasks/{id}`, task `complete` and `reopen` actions, `GET|POST /api/v1/events`, `GET /api/v1/status`, `GET /api/v1/export`, `POST /api/v1/restore`, `POST /api/v1/backups`, backup-schedule `GET|POST|DELETE /api/v1/backups/schedule`, and `GET /api/v1/doctor`. Local text generation remains at `POST /v1/chat/completions`, and the sample text processing route is `GET /process?input_data=...`. These routes are served by `aether-server` or `uvicorn app:app`, not by the standalone Historian dashboard. The task/event, status, export/restore, backup, schedule, and doctor endpoints call the same storage and maintenance logic as the CLI. Restore replacement creates a safety backup before replacing non-empty data. Backup and schedule changes use the project’s protected local backup directory and scheduler implementation.

Cross-origin requests are denied by default; set `AETHER_CORS_ORIGINS` to a comma-separated list of trusted browser origins only when needed. Inference is serialized because the local model backend is not assumed to be safe for concurrent calls. The service returns HTTP 503 when model weights or the local inference backend are unavailable. Token usage and tool calling are not reported because the current inference engine does not provide those features. CI and the full test suite install the development, API, secure-vault, and spin-network-visualization extras.

The experimental behavior-model utility is grouped with the production historian module at `src/aether_engine/historian_behavior.py`. Run its safe model-path scan with `aether-historian-behavior --scan-root .` or `python -m aether_engine.historian_behavior --scan-root .`; training is opt-in with `--train` and requires the optional PyTorch dependency (`python -m pip install -e ".[behavioral-demo]"`). Training is capped at 1,000 steps and is a small character-level demonstration, not the Qwen GGUF inference backend. To query the local Ollama model and review the supplied historian archive, run `aether-historian-behavior --telemetry`; it defaults to `aethersystem-core` at `localhost:11434`, allows up to 300 seconds for local inference (configurable with `--ollama-timeout`), accepts `--ollama-host`, `--ollama-port`, and `--ollama-model`, and refuses non-loopback hosts. The archive is explicitly presented as unverified input so the model does not treat the supplied historical claims as facts. Automated tests for the utility remain in `tests/test_historian_behavior.py`.

The spin-network boundary calculation is available as `aether-spin-network` or
`python -m aether_engine.spin_network_boundary`. Install its NumPy dependency
with `python -m pip install -e ".[spin-network]"`. It accepts optional
`--num-links` and `--seed` arguments; defaults are 30 links and seed 42.
Create a PNG boundary visualization as a base64 data URI with
`aether-spin-network-visualize` or
`python -m aether_engine.spin_network_visualization`. Install its optional
NumPy and Matplotlib dependencies with
`python -m pip install -e ".[spin-network-visualization]"`.

The optional `aether_engine.secure_vault.JesterShieldVault` encrypts strings
with Fernet and requires an access token supplied by the caller. Install its
dependency with `python -m pip install -e ".[secure-vault]"`. Its default
encryption key is generated per instance; provide a securely stored Fernet key
when encrypted payloads must remain decryptable across instances or restarts.

`aether_engine.telemetry.SystemTelemetryLogger` records execution events to a private `aether_events.jsonl` file and asks the local `aethersystem-core` Ollama model to analyze events marked `EXCEPTION` or containing an `error` detail. Install its optional SDK with `python -m pip install -e ".[ollama]"`. Events are recorded before inference, so they remain available if Ollama is offline; analysis connects only to `127.0.0.1:11434`.

## Usage

```bash
# Record and review project history
aether-engine event add "First milestone completed" --topic release
aether-engine event list --limit 10
aether-engine event list --search build --topic release --since 2026-11-01

# Create, review, and complete tasks
aether-engine task add "Write the getting-started guide" --description "Include install and CLI examples" --priority high --due 2026-12-01
aether-engine task list --status pending --search guide
aether-engine task edit 1 --priority normal --due 2026-12-10
aether-engine task complete 1
aether-engine task reopen 1

# See task progress and recent project activity together
aether-engine status

# Check database, backup, permissions, and scheduled backup health
aether-engine doctor

# Export a portable JSON copy (prints to stdout if no file is given)
aether-engine export project-backup.json

# Create a dated backup in .aether-backups/
aether-engine backup --keep 30
aether-engine backup schedule install --keep 30
aether-engine backup schedule status

# Remove the daily schedule
aether-engine backup schedule uninstall

# Restore into a new/empty project database
aether-engine restore project-backup.json

# Intentionally replace existing tasks and events
aether-engine restore project-backup.json --replace
```

The `--priority` option accepts `low`, `normal` (the default), or `high`. The optional `--due` date must use `YYYY-MM-DD`; overdue tasks are highlighted on the status dashboard. CLI and API completion percentages are based on all tracked tasks: they reach 100% when every task is done and remain 0% when there are no tasks.
Edit tasks with `task edit ID` and one or more of `--title`, `--description`, `--priority`, or `--due`; use `--clear-due` to remove a due date. Task `--search` matches titles and descriptions; event `--search` matches topic and message, and event history can also be filtered by exact `--topic` and inclusive UTC `--since`/`--until` dates.

Task and event text is trimmed and sanitized before it is saved, including on task edits and restores. Blank task titles and blank event topics/messages are rejected with a clear error. Common leading shell prompts and trailing backticks/Markdown closing markers are removed; inner shell operators such as `&&`, `;`, and `|` are preserved.

`aether-engine backup` writes a timestamped JSON snapshot to `.aether-backups/` beside the selected database; pass `--directory PATH` to choose another folder. It keeps the newest 30 timestamped Aether backups by default, pruning older Aether snapshot files after a successful backup. Set `--keep N` to change the limit; it must be at least one. On POSIX, backup directories are restricted to owner-only access (`700`), snapshots, scheduler logs, and the SQLite database/WAL files to owner read/write (`600`). On Windows, SQLite database/WAL files have inherited ACLs replaced with a full-control grant for the current user. Unrelated files in the backup directory are left alone. Replacing a non-empty database with `restore --replace` first creates a safety backup automatically, subject to the same retention policy. JSON exports include tasks, events, and a schema version. Exporting to a new file is the default; pass `--force` only when intentionally replacing an existing file.

On macOS, `aether-engine backup schedule install` installs a per-project user LaunchAgent; on Linux it installs one marked entry in the current user's crontab. Both run backups daily at **9:00 AM local time**, use the current Python environment and explicit database path, and retain 30 snapshots by default. Set a different scheduled retention with `aether-engine backup schedule install --keep N` (reinstall the schedule to apply a changed value). `backup schedule status` reports whether the schedule is installed and the last run's exit code; remove only Aether's entry with `aether-engine backup schedule uninstall`. On Windows, use Task Scheduler with a daily 9:00 AM trigger, program `C:\path\to\project\.venv\Scripts\python.exe`, arguments `-m aether_engine --database "C:\path\to\project\.aether-engine.sqlite3" backup --keep 30`, and the project directory as **Start in**. The built-in schedule install/status commands are not available on Windows.

`aether-engine doctor` performs read-only checks of the selected database and its OS-appropriate permissions, newest backup validity, backup permissions, and supported scheduled-backup status/last exit code. Missing backups or an uninstalled schedule are reported as warnings; detected corruption, insecure permissions, or a failed installed schedule make the command exit nonzero. On Windows, manual Task Scheduler setup is reported as a warning because the built-in schedule management commands are unavailable. The doctor does not format or modify project source files.

SQLite schema changes are applied by numbered migrations recorded in `PRAGMA user_version`. The engine upgrades older databases transactionally and refuses to open databases created by a newer unsupported schema version.

The optional experimental supervisor can be started with `python -m aether_engine.supervisor` inside the project virtual environment. It computes resonance over in-memory sample telemetry only; it is not connected to the project database, does not install itself as a background service, and does not monitor real system telemetry. It writes `aether_runtime.log` in the current directory, checks Ruff lint at startup and then every five minutes, and handles Ctrl-C/SIGTERM for graceful shutdown. Its maintenance check is read-only and never auto-fixes source files.

For an optional off-machine copy, `backup_replication.py` makes a real versioned JSON snapshot from an existing Aether database, then can send that snapshot using your configured SSH agent/config. Run from the project directory:

```bash
python backup_replication.py --database .aether-engine.sqlite3
python backup_replication.py --database .aether-engine.sqlite3 \
  --remote-user BACKUP_USER \
  --remote-host backup.example.net \
  --remote-dir /srv/backups/aether
```

Without all three remote options it runs local-only and never contacts a host. The remote destination directory must already exist and be writable. An SSH key can optionally be selected with `--identity-file`; otherwise OpenSSH uses its normal SSH configuration/agent. Tests exercise a real SCP transfer to an ephemeral sshd bound only to loopback; configure your own trusted SSH host for off-machine use.

Use `--database PATH` before the command to select a different SQLite database. For example:

```bash
aether-engine --database ./data/project.sqlite3 task list
```

Restore validates the full versioned backup before writing. It refuses to modify a non-empty database unless `--replace` is provided; replacement is transactional, so invalid data does not partially replace existing records.
