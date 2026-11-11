# Portable Aether demo

This fictional community-garden project demonstrates tasks, event history,
search, and the status dashboard using only Aether's core local CLI and SQLite
store. It contains no personal history or credentials and needs no model server,
network access, or optional dependencies.

Install the core package from the repository root if you have not already:

```sh
python -m pip install -e .
```

From the repository root, load the sample into a dedicated demo database and
explore it:

```sh
python -m aether_engine --database examples/demo/.aether-engine.sqlite3 restore examples/demo/sample-project.json
python -m aether_engine --database examples/demo/.aether-engine.sqlite3 status
python -m aether_engine --database examples/demo/.aether-engine.sqlite3 task list
python -m aether_engine --database examples/demo/.aether-engine.sqlite3 event list
python -m aether_engine --database examples/demo/.aether-engine.sqlite3 task list --search garden
```

The restore command only imports into an empty database. It refuses to replace
existing records, so the demo cannot silently overwrite project history. To
start over, remove only `examples/demo/.aether-engine.sqlite3` and its possible
SQLite `-wal` and `-shm` sidecar files, then rerun the restore command.

To try creating and completing your own task, use the same `--database
examples/demo/.aether-engine.sqlite3` option with `task add`, `task complete`,
or `event add`. The sample JSON stays unchanged.
