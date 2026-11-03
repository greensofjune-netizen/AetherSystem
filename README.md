# Aether Engine

A local-first command-line tool for tracking project tasks and recording a searchable event history. By default, data is stored in `.aether-engine.sqlite3` at the nearest parent directory containing `pyproject.toml`; outside a project, it is stored in the current directory. Each project therefore gets its own database.

## Install and test

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

On Windows, activate with `.venv\Scripts\activate` instead.

The editable install exposes the `aether-engine` command from this checkout. After code changes, rerun `python -m pytest`; to verify the installed command, run `aether-engine --help`.

To copy the current engine source, tests, and project configuration into another directory without overwriting existing files, run `python seed_project.py --target ../new-aether-project`.

The optional `aether_engine.ai_bridge.AetherLunaBridge` runs in offline simulation mode by default; try it with `python -m aether_engine.ai_bridge`. It does not send requests to OpenAI, and its default `gpt-6-luna` identifier is a caller-provided label, not a verified available model. Live provider integration requires an explicitly supplied transport callable and API key; no OpenAI SDK or live provider adapter is included.

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

The `--priority` option accepts `low`, `normal` (the default), or `high`. The optional `--due` date must use `YYYY-MM-DD`; overdue tasks are highlighted on the status dashboard.
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
