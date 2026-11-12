# Aether Engine

Aether Engine is a local-first project tracker: manage tasks and keep a searchable
history of project events from the command line. Start here; the desktop apps,
AI chat, dashboards, calculators, and archives below are optional experiences.

## Start here

From the project directory, install the CLI into a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate with `.venv\Scripts\activate` instead. Then try the full
task-and-history loop:

```bash
aether-engine task add "Ship my first project"
aether-engine task list
aether-engine event add "Started tracking this project" --topic progress
aether-engine status
```

These commands use a local SQLite database and need no model server, cloud
account, or optional dependencies. By default, data is stored in
`.aether-engine.sqlite3` at the nearest parent directory containing
`pyproject.toml`; outside a project, it is stored in the current directory.
Use `aether-engine --help` to explore commands.

For the system schematic, component boundaries, operation sequences, and
verification checklist, see [System operations](./SYSTEM_OPERATIONS.md).

Try the [fictional community-garden demo](./examples/demo/README.md) in its own
database without importing or sharing your real project history.

## License and release scope

Original Aether Engine material is licensed under the [MIT License](./LICENSE).
Third-party materials retain their own terms; see
[third-party notices](./THIRD_PARTY_NOTICES.md).

The initial release target is the source repository and core local CLI.
Optional desktop apps and hosted services are separate release targets, not
certified or production-ready by virtue of the core tests passing. CI checks
Python 3.11 and 3.14 on macOS and Linux; Windows instructions are provided, but
Windows is not currently tested in CI.

Runtime metrics (`aether_metrics.json`), the Matrix simulation log
(`historian_telemetry_vault.json`), and the generated knowledge ledger
(`ingested_knowledge.txt`) are local outputs, not bundled public samples.
They are excluded from the current release tree and Python archives. Earlier
commits still contain historical versions; these exclusions do not erase history.
Do not mirror-push local `refs/agents/` checkpoint refs, which can retain
developer snapshots and old build artifacts outside the release branch.

Before publishing:

- Review the exact commit, including staged versus unstaged changes, and confirm
  ownership and redistribution terms for all included materials.
- Keep private databases, exports, telemetry, secrets, installers, and build
  caches out of the public commit. Archive exclusions do not remove files from
  Git history or the GitHub source tree.
- Run `ruff check .`, `mypy`, and `python -m pytest` in the development environment.
  The distribution test builds a source archive and a wheel from that archive,
  checks the MIT license and private-file exclusions, and exercises the core
  CLI and demo from a fresh wheel installation without optional dependencies.
- With Node.js 24, run `node --test tests/test_validation_frontend.mjs` and
  `node tests/test_validation_types.ts`. CI also checks the validation model
  with TypeScript 5.9.3; these tests protect the structured HTTP 422 contract.
- Build release files with `python -m build` after installing the development
  dependencies. This writes the source archive and wheel to `dist/`; review
  their contents and test the exact files intended for upload.
- Select and review a versioned release candidate before tagging or uploading.
  No automatic publishing workflow is configured.

## Optional companion experiences

### Standalone Quantum Light Lab

Open [Quantum Light Lab](./quantum-lab/index.html) directly in a browser for an
offline double-slit simulation with individual photon detections, interference
graphs, which-path controls, and entropy/surprisal charts. It has no Aether
runtime or external dependencies. All results are explicitly simulated, not
measurements of real quantum entropy. See the [lab guide](./quantum-lab/README.md)
for the physics model, limitations, controls, and tests.

## Matrix Aristotle desktop companion

Matrix Aristotle unifies Galileo's persistent chat and multimodal controls,
Copernicus weather and astronomy, Historian archive search, and Matrix
simulation/Automator views in one macOS window with the same ember-and-gold
design. It reuses Galileo's existing conversation directory and does not migrate
or combine the separate historical archive, Matrix telemetry, or Copernicus
browser-session chats.

```bash
.venv/bin/python build_aristotle.py --output-dir dist/aristotle-ready
open "dist/aristotle-ready/Matrix Aristotle.app"
```

The build requires the existing desktop/build dependencies and Swift compiler,
is ad-hoc signed, and refuses to overwrite an existing app. It is not signed
with a Developer ID or notarized and is **not ready for public distribution**.
For a test bundle that does not use the build machine's project as its default,
pass `--portable`; its default linked project becomes
`~/Library/Application Support/AetherSystem/Matrix`. This location is not
populated automatically. Set `AETHER_PROJECT_PATH` or pass `--project-directory`
when launching to use a real project; project actions, archive, and telemetry
will be unavailable until the required files exist there. There is currently no
in-app project picker. Public distribution still requires a Developer ID
Application identity, hardened-runtime signing, Apple notarization and
verification on another Mac.

Ollama must be
running; the default Atlas coder model is text-only, so select a vision model
for images. To run from source use
`.venv/bin/python -m aether_engine.aristotle_desktop`; the native dictation
helper is compiled automatically in the app bundle, and source runs need a
compiled `src/aether_engine/galileo-voice`.

The History view searches the project's existing `universal_history.sqlite3`
read-only, or the path in `AETHER_HISTORY_ARCHIVE`. A missing archive is reported,
not created. Archive records are unverified; they enter a chat prompt only when
you check the archive option for that message. The Matrix view reads simulated
telemetry from `historian_telemetry_vault.json` (or
`AETHER_HISTORIAN_LOG_FILE`) and has its own in-process simulated governor;
it does not control the separate dashboard's governor or enforce hardware
limits. Tests and backups still require explicit native confirmation. The
linked project defaults to the build project's path and can be overridden with
`AETHER_PROJECT_PATH` or `--project-directory`. Weather uses Open-Meteo and
requires network access; voice input requires on-device macOS speech support
and microphone/speech permission.

## Matrix agent governor

The master dashboard includes an **Agent Governor** with simulated Astronomy,
Propulsion and History routing and a horizontal chart of illustrative memory
estimates. The default total is 4.1 GB (1.2 + 1.5 + 0.8 + 0.6); 5.3 GB is an
informational reference only. Nothing is executed, allocated, measured, or
enforced. The case-insensitive `exploit` / `unauthorized_tracking` keyword
screen checks the description, domain, and JSON payload, but it is not a
security control or a guarantee of ethical behavior.

On the running loopback Matrix dashboard, `GET /api/matrix/governor/allocations`
returns both `chart` and a Base64-encoded JSON `chartjs_spec`.
`POST /api/matrix/governor/route` accepts JSON fields `task_description`,
`domain`, and `execution_payload`. Results are `SIMULATED`, `REJECTED`, or
`UNROUTABLE`; the bounded in-memory log holds outcomes and node IDs, not
submitted descriptions or payloads, and is reset on restart.

In the master dashboard's Copernicus and Stargazer chat views, each valid
submitted prompt is screened and sent to the governor using simple local
keyword-based domain inference. Prompts matching multiple domains or none are
shown as unroutable rather than guessed. The chat displays the simulated route,
verification against the active registry, and timestamp; no agent is executed,
and this is not a security guarantee. Telemetry stays in the current chat view
and in the governor's bounded in-memory outcome log; it is not saved with chat
or supplied to the language model. Routing can still be displayed if the
subsequent local model request fails.

The dashboard Copernicus chat also offers five local conversation personas:
Copernicus, Scribe, Propulsion Lead, Ecosystem Governor, and Cosmic Jester.
Selection changes the chat accent and adds a server-owned style instruction
to the configured Ollama model; it does not change models, synthesize a
different audio voice, or give the assistant access to tools. The selection
lasts for the open page and is not persisted. Other chat surfaces retain their
existing default. Governor behavior and hardware limits remain simulated.

```bash
curl -s http://127.0.0.1:8000/api/matrix/governor/route \
  -H 'Content-Type: application/json' \
  -d '{"task_description":"Describe a sky observation","domain":"Astronomy","execution_payload":{"target":"Rigel"}}'
```

## Galileo desktop test drive (macOS)

**Galileo** is the native desktop LLM companion, separate from the Copernicus
evaluation shell. It retains the Matrix-inspired ember-and-gold look. Chat has
no access to Matrix internals or private telemetry; separately confirmed
desktop actions connect Automator to Matrix.

```bash
python -m pip install -e ".[desktop,build]"
python build_galileo.py --output-dir .
open Galileo.app
```

The build produces a macOS `.app` for the build machine's architecture.
It is locally ad-hoc signed, not Apple-notarized for public distribution.
The build refuses to overwrite an existing `Galileo.app` in its output directory;
choose another output directory for later builds. Without `--output-dir` it
uses `dist`.
Ollama must already be running on `127.0.0.1:11434`; Galileo preloads the
already-installed `atlas-qwen-coder:latest` text model when the app starts and never pulls a
model or sends chat to a cloud provider. Register the GGUF from
`/Volumes/Atlas/models` with Ollama once. Select an installed
vision model such as `qwen3.5:4b` for images. The model and preload state are shown in the chat
interface; another installed model can be selected in the app.
Start from source with
`python -m aether_engine.galileo_desktop`, or use `--browser` for a development
preview. `--model NAME` selects the initial model. Source runs require the
compiled `src/aether_engine/galileo-voice` helper for native dictation; the
desktop build compiles and bundles it automatically using `swiftc`.

Enter sends a message; Shift+Enter inserts a new line, including in the native
WebKit window with IME composition protection. **Stop response** interrupts
only that chat's Ollama request and prevents a stopped exchange from being
saved. **Retry draft** resends the preserved draft and attachments after a
failure or stop; a retry may briefly report an active response while the
previous request unwinds. Responses can be copied or read aloud, with a
separate stop-reading control. A chat containing saved images must continue
with a vision-capable model.
Galileo explicitly disables hidden model thinking for chat and camera requests
so the output-token budget is available for the visible answer.

**Matrix actions** exposes only project tests and local backups through the
same Automator bridge as the installed Quick Actions. Each action requires a
macOS confirmation dialog; no model-generated commands are executed. Action
metadata (name, outcome, duration, model) goes to the project's Aether event
store under `automator`, node `MATRIX`, without chat or backup contents.
The bundle links to the source project used during its build; move it only
with `--project-directory PATH` or `AETHER_PROJECT_PATH` configured.

The frozen app runs project tests with the linked project's `.venv/bin/python`,
not its own bundled executable; prepare that environment before using the action.

Test the complete flow: refresh the connection, send a message, ask a follow-up
that depends on the conversation, attach a text file and an image, try voice
input, create another chat, and reopen the first conversation. Quit and reopen
Galileo to verify persistence. Weather requires internet access to Open-Meteo.
In **Formula Lab**, try the state-vector circuit simulator, the separate legacy
quantum index, seeded spin-network boundary, and radio line-of-sight calculators.
The circuit tool supports common single-qubit and controlled gates, full
state-vector output, and reproducible measurement shots.
Stargazer's **Visible stars** view calculates local positions from the JPL DE421
ephemeris and Hipparcos catalog; the first observation downloads these data and
caches them in the user's application cache, outside the project. No astronomy
API is called. The existing
Copernicus comms panel in Stargazer is not a second Galileo chat; use Galileo's
**Chat** tab for saved conversations and attachments. Use the sidebar's ×
control to permanently delete a conversation and its messages.

Galileo's **Astrology** tab calculates a tropical natal chart with geocentric
planetary positions and whole-sign houses, plus Pythagorean life path, birthday,
expression, soul urge, personality, and maturity numbers. Enter the local birth
date and time, an IANA time zone, decimal latitude/longitude, and the name at
birth. Name-based numerology supports Latin letters; diacritics are normalized.
Historical time-zone transitions are handled explicitly: skipped times are
rejected, and the form lets you choose the first or second occurrence of a
repeated time. This feature is
interpretive, not evidence-based prediction.

In Galileo, chart requests go only to its loopback server and are not saved to
chat, the Aether database, or Historian. Location is entered manually; Galileo
does not send birth details to a geocoder or other third-party service. The
shared calculation is also available through `POST /api/v1/astrology/chart` on
the Aether API; that endpoint uses the configured Aether server, so callers
should send birth details only to a server they trust. The API does not persist
the submitted birth details.

The **Formula Lab** tab runs a local state-vector simulation through
Galileo's loopback API, with a maximum of 12 qubits, 256 gates, and 10,000
measurement shots per request. It supports H, X, Y, Z, S, T, RX, RY, RZ, CNOT,
and CZ. Qubit 0 is the least-significant state-vector bit; displayed bit strings
run most-significant bit first. Seeded measurement counts are reproducible.
This is exact circuit math, not a model of quantum hardware, noise, or a real
device. The separate scalar coherence/entropy index is illustrative; the
spin-network sample is seeded and simplified; and the radio estimate omits
terrain, buildings, weather, antenna patterns, and measured signal strength.
Inputs and results are not saved or sent to chat.
Visible-star astronomy remains in **Stargazer**, while natal-chart and
Pythagorean numerology calculations remain in **Astrology**. Propulsion
equations in the archive are user-supplied reference data and are not executed.

Chats and attached text/images are saved in
`~/Library/Application Support/Galileo/conversations.sqlite3`, separately from
the Aether task database. The directory is owner-only (`700`) and database/log
files are owner-read/write (`600`). Storage is not encrypted at rest; use
FileVault for disk encryption and do not attach secrets. `--data-directory PATH`
or `GALILEO_DATA_DIR` selects a different location. Close the native window to
stop its private HTTP server; it binds an ephemeral loopback port and requires
a per-launch session cookie. No background service is installed. Native voice
uses macOS on-device-only dictation after explicit microphone and speech
permission. It never uploads audio or sends text automatically; review the
transcript first. Dictation ends after a bounded recording or when you choose
**Finish voice input**. If macOS lacks on-device language support, it reports
that explicitly without a cloud fallback. Native read-aloud uses macOS `say`.
Browser voice
recognition is feature-detected and may use the browser vendor's speech service;
it is not sent to Galileo until you submit the transcribed text.

The **Camera** tab can periodically describe the Mac's camera view using the
local `qwen3.5:4b` vision model. The camera is off until the user starts it;
leaving the tab, stopping it, or closing the page stops capture. Frames are sent
only to the local Galileo server and Ollama and are not saved to chat or disk by
Galileo. Analysis is periodic and may be slow or inaccurate: it is not a
real-time safety system and cannot control devices. macOS camera permission is
required; camera support depends on the native webview. If unavailable, start
Galileo with `--browser` and open its printed loopback address in a compatible
browser. Explicitly saved camera preferences are stored locally in the same
Galileo database and can be individually deleted; they guide later observations
but do not retrain the model. They are not encrypted at rest.
If Qwen cannot load because memory is insufficient, the Camera tab stops and
displays the Ollama error. A smaller installed text model can still be selected
for chat, but it does not replace the camera's vision model.

Supported attachments: UTF-8 `.txt`, `.md`, `.py`, `.js`, `.ts`, `.json`, `.csv`,
`.log`, `.html`, `.css`, `.yaml`, `.yml`, and `.toml`, plus JPEG, PNG, and WebP
images. Limits are 10 text files (60,000 bytes per file, 120,000 bytes total),
4 images (2 MB each, 6 MB total), 16 MB of images per conversation, and 8,000
characters per message. Image attachments require a model with vision support.
The LLM receives the saved conversation and explicitly selected attachments
only. Failed inference does not append a partial exchange; a conversation over
the 240,000-byte text-context budget must be continued in a new chat. Model
context windows may impose smaller limits.

Validate with `python -m pytest`, `ruff check .`, and `python -m mypy`.

### macOS Automator Quick Actions

For the Aristotle internal pilot, install a separate **Aristotle - Launch**
Quick Action that opens the built app directly:

```bash
python3 automator/install.py --app-bundle "dist/aristotle-internal-pilot/Matrix Aristotle.app"
```

This installs only the Aristotle launcher and leaves existing Galileo workflows
unchanged. The launcher does not need Python at runtime or grant chat any tools.
Keep the bundle at its installed path; if you move it, remove only
`~/Library/Services/Aristotle - Launch.workflow` after reviewing it, then reinstall
with the new path. Enable it in macOS Keyboard Shortcuts > Services if needed.
Ollama must be running for chat. This remains a locally ad-hoc-signed pilot,
not a notarized public release; do not disable Gatekeeper for distribution.

Install the local, manually triggered Services menu actions from the project
directory, using the Python environment that has the project and test
dependencies installed:

```bash
.venv/bin/python automator/install.py
```

In an application's **Services / Quick Actions** menu, use **Galileo - Launch**,
**Galileo - Ask Local LLM**, **Galileo - Ask About Selected Text**, **Galileo -
Run Project Tests**, or **Galileo - Back Up Local Data**. Enable them in macOS
Keyboard Shortcuts > Services if macOS does not show them immediately. The
selected-text action requires selected text; the other chat action asks for a
prompt. Chat sends only the current text to `atlas-qwen-coder:latest` on local
Ollama and does not save it in Galileo or use conversation history. The
selected-text action asks for confirmation before sending. Ollama must already
be running. Do not send sensitive text.

The test and backup actions ask for confirmation. The backup action uses
consistent SQLite snapshots, then writes an Aether JSON export to this project's
`.aether-backups/` and a Galileo SQLite backup to
`~/Library/Application Support/Galileo/Backups/`; `GALILEO_DATA_DIR` can
override the Galileo directory when inherited by the workflow. Both existing
databases must be present. Aether keeps its standard 30-backup retention;
Galileo snapshots are not automatically pruned. Backups and selected prompts
are not encrypted; use FileVault and protect backup copies. To restore an
Aether snapshot use `aether-engine restore`; restore a Galileo SQLite snapshot
only after closing Galileo, and preserve the original database first.

No background service or remote listener is added. These actions execute the
project's local Python files with the interpreter selected during installation;
reinstall them if the project or interpreter moves. The installer refuses to
overwrite existing workflows. To remove them, delete the five named
`Galileo - *.workflow` items in `~/Library/Services/`; review existing files
before deleting anything.

## Install and test

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,api,secure-vault,spin-network-visualization]"
python -m pytest
```

On Windows, activate with `.venv\Scripts\activate` instead.

The editable install exposes the `aether-engine` command from this checkout. The development, API, secure-vault, and spin-network-visualization extras install the dependencies needed by the full test suite. After code changes, rerun `python -m pytest`; to verify the installed command, run `aether-engine --help`.

To refresh every optional dependency group in an existing environment, run:

```bash
python -m pip install --upgrade --upgrade-strategy eager -e ".[dev,build,local-ai,api,calculator-api,behavioral-demo,command-center,ollama,spin-network,spin-network-visualization,secure-vault,desktop]"
python -m pip check
python -m pytest
```

Core and optional dependency minimums are maintained in `pyproject.toml`.
Python 3.11 and newer remain supported; CI checks Python 3.11 and 3.14.

### Aether engine layout

The request flow is split into capability orchestration, domain engines, and
model providers. `engine_core.EngineOrchestrator` dispatches typed
`EngineCapability` handlers; `formula_routes.py` registers the quantum,
spin-network, and radio-link calculations there. The deterministic simulator
lives in `quantum_engine.py`, while read-only host and project checks live in
`system_diagnostics.py`. `quantum_simulator.py` remains a compatibility facade
for existing imports and the diagnostics command.

Each FastAPI application owns an `EngineRuntime` that starts and stops with the
app, dispatches formula capabilities, routes typed chat/model operations, and
reports bounded metrics. Galileo uses the loopback-only `OllamaProvider`; the
main Aether API routes text to its local GGUF engine and image chat to Ollama.
The calculator API shares the formula runtime without loading a model.
`/api/engine/status` (Galileo and calculator) and
`/api/v1/engine/status` (Aether API) expose runtime state and aggregate metrics.
Every HTTP response includes an `X-Request-ID`; structured request logs include
the ID, endpoint metadata, status, and duration, but never request bodies,
prompts, or attachments.

Inference defaults to one active request, two queued requests, and a 15-second
queue deadline. Full or expired queues return HTTP 429. Set
`AETHER_MAX_CONCURRENT_INFERENCES`, `AETHER_MAX_QUEUED_INFERENCES`, and
`AETHER_INFERENCE_QUEUE_TIMEOUT_SECONDS` to adjust the scheduler. Ollama HTTP request and preload timeouts default to 120 and 300 seconds, configurable with
`AETHER_MODEL_REQUEST_TIMEOUT_SECONDS` and
`AETHER_MODEL_PRELOAD_TIMEOUT_SECONDS`. Generated output is capped at 2,048 tokens by default
(`AETHER_MAX_OUTPUT_TOKENS`); Galileo camera descriptions remain capped at
1,024. The chat text-context limit remains 240,000 UTF-8 bytes. The local GGUF
backend also retains its 4,096-token context cap and is bounded by the same
output-token limit; it does not currently have an interruptible wall-clock
generation timeout, so the queue deadline applies before generation starts.
Deterministic formula and provider-contract evaluations run without a live model;
they verify behavior and interfaces, not model-answer quality.

There is no xAI/Grok provider: this layout uses general public runtime patterns
and does not claim to reproduce Grok's unpublished serving internals.

## Build a standalone executable

Install the optional build dependency with `python -m pip install -e ".[build]"`, then run `python build_app.py`. PyInstaller writes the executable to `dist/`; the build targets the operating system and architecture of the Python interpreter used to run the script. Check the result with `./dist/aether-engine --help` on macOS and Linux.

To copy the current engine source, tests, and project configuration into another directory without overwriting existing files, run `python seed_project.py --target ../new-aether-project`.

The optional `aether_engine.ai_bridge.AetherLunaBridge` runs in offline simulation mode by default; try it with `python -m aether_engine.ai_bridge`. It does not send requests to OpenAI, and its default `gpt-6-luna` identifier is a caller-provided label, not a verified available model. Live provider integration requires an explicitly supplied transport callable and API key; no OpenAI SDK or live provider adapter is included.

`aether_engine.ai_bridge.LocalAirGappedEngine` defaults to the official Qwen2.5-Coder-1.5B Q4_K_M GGUF at `models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`. Download the weights from [Qwen's official Hugging Face repository](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF) if they are not already present; the approximately 1.1 GB GGUF files are excluded from Git. Install the optional backend with `python -m pip install -e ".[local-ai]"`, or set `AETHER_MODEL_PATH` to an alternate GGUF file. The engine loads the model on first inference and makes no network requests; vision inference is not supported by this text model.

The local REST API is available with `python -m pip install -e ".[api]"`. Run the full API with `uvicorn app:app --reload` during development or `aether-server` for the packaged entry point. Both listen on `127.0.0.1:8000` by default. Loopback clients are trusted; non-loopback clients must send a matching `X-Aether-Token` header. Set a high-entropy `AETHER_API_TOKEN` in the server environment before binding Uvicorn to a network interface. An unset token denies remote requests. Set `AETHER_DATABASE_PATH` to select the SQLite database; otherwise the API uses the nearest project `.aether-engine.sqlite3`. Interactive OpenAPI docs are at `/docs`. The shared script is available at `/aether_client.js`; serving it does not automatically load it into a page or implement the dashboard and Copernicus endpoints it references.

### Local Workspace record bridge

`workspace_matrix_bridge.py` sanitizes caller-supplied Google Workspace-style
records; it does not call Google APIs or make network requests. It keeps only
the event ID and summary, drops unrecognized metadata, and uses a simple
keyword blocklist that is not a comprehensive safety review. Cleared summaries
are written only to the local Aether event store; blocked records are not
persisted. Preview the included sample feed without writing with
`python workspace_matrix_bridge.py --dry-run`. To persist that sample locally,
run `python workspace_matrix_bridge.py` or pass `--database PATH`; the default
database is `AETHER_DATABASE_PATH` or this project's `.aether-engine.sqlite3`.
Galileo's **Workspace import** tab accepts a pasted JSON array or a local JSON
file, offers a no-write preview, then stores only cleared summaries in the
local Aether event database. Its API is loopback-only and requires the Galileo
session cookie; the tab makes no Google or Cloudflare requests. In Galileo, the
default event database is `.aether-engine.sqlite3` inside its local data
directory; `AETHER_DATABASE_PATH` overrides it. Imports are limited to 100
records and 1.5 MB. The keyword filter is only a heuristic, so review records
before importing.

### Aether Engine API website (Cloudflare Workers)

The static documentation page is in `website/wix-embed.html`; `worker/index.js`
wraps it as a complete HTML page and serves it from the root of
`aetherengineapi.com.co`. `wrangler.jsonc` configures static assets and custom
domains for both the apex and `www` host, with `www` redirected to the apex.
The public apex and `www` routes remain documentation-only.

### Private calculator API

`aether_engine.calculator_api:app` is a separate, stateless FastAPI service for
the quantum, seeded spin-network, and radio line-of-sight calculators. It does
not load chat, Workspace import, or the Aether event store. Formula routes
require an `Authorization: Bearer ...` token on every request, including
loopback requests; only `/health` is unauthenticated. API documentation is
disabled and request bodies are limited to 64 KB. `requirements.txt` selects
the `calculator-api` dependency extra for Azure's remote build.

The calculator-only browser UI is in `website/calc/` and is served at
`calc.aetherengineapi.com.co`. The Worker proxies only the three calculator
routes to an HTTPS `API_ORIGIN`, injecting the `API_TOKEN` Worker secret;
neither secret is sent to the browser. The App Service setting
`AETHER_CALCULATOR_TOKEN` must match the Worker secret. Keep both out of source
control and chat. The calculator page warns that entered values reach the
hosted API; do not enter sensitive personal data.

The Worker returns `404` for the entire calculator hostname unless its
`CALCULATOR_ACCESS_ENABLED` setting is exactly `true`. Leave it unset until
Cloudflare Access is enabled and its allow policy is active.

Before deploying the calculator hostname, enable Cloudflare Access, create a
self-hosted Access application for `calc.aetherengineapi.com.co`, and allow only
the intended users. Set the App Service startup command to
`python -m uvicorn aether_engine.calculator_api:app --host 0.0.0.0 --port 8000`,
enable `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, and configure
`AETHER_CALCULATOR_TOKEN` as an App Service application setting. Then set the
Worker secrets `API_ORIGIN` (the HTTPS App Service root origin) and `API_TOKEN`
(the same token), and set `CALCULATOR_ACCESS_ENABLED` to `true`, only after the
Access application and allow policy are active. `wrangler.jsonc` attaches the
calculator hostname whenever the Worker is deployed; do not deploy it before
Access is configured.

The private calculator route is separate from the public documentation host.
Check App Service P0v3 pricing and quota before creating a plan. The local
development environment must have the current Azure CLI installed and
authenticated before Azure provisioning; no cloud resources are created by
this repository's local test flow.

Ensure the domain's zone is active in the same Cloudflare account that will
host the Worker. The deploy command attaches the apex, `www`, and calculator
custom domains; configure Access for the calculator hostname before deploying.
Then install Node.js/npm and run from the project root:

```sh
npx wrangler@latest login
npx wrangler@latest deploy
```

The configured routes attach the apex and `www` host as Worker custom domains;
Cloudflare manages their DNS records and TLS certificates. This project does
not attempt to register or purchase a domain. The API remains loopback-only
unless a separate production deployment and security review is completed.

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
At startup it preloads the already-installed `qwen3.5:4b` model from local
Ollama without pulling it. Install it with `ollama pull qwen3.5:4b` before
launching, or use `--ollama-model NAME` to select another installed model.
Chat sends the current typed message and up to six recent successful
turns from the open tab for continuity; this temporary context is never written
to disk and clears on reload or **New chat**. When available, the latest
cloud-cover reading is also sent; selected images go only with the current
message and are not saved. Saved entries and earlier browser sessions are not
sent. Replies disappear on reload. Copernicus has no persistent profile or
memory and has no technical connection to Matrix data or controls. Requests are
serialized, have a 120-second backend timeout,
and report failures without affecting shell navigation. Model preload status is
shown in the chat. The health route reports AI configuration, not verified
model availability. Browser voice recognition may use the browser vendor's
speech service; transcribed text is sent only when submitted.
The non-disclosure instruction is a behavioral prompt, not a guaranteed
formula/content filter; keep the model isolated and do not paste proprietary
material into chat. This is still a local evaluation interface, not certified
for commercial disclosure prevention. Edit `frontend/copernicus.js` for chat
interactions and `historian_matrix.py` for the independent shell routes.

### Historical archive

The separate `universal_history.sqlite3` database stores historical entities,
tags, and directed connections; it does not modify `.historian-matrix.sqlite3`
or store chat history. Create it and insert the supplied example records with:

```sh
python history_matrix_archive.py --seed
python history_matrix_archive.py --year -2500
python history_matrix_archive.py --year -2500 --region "South Asia"
```

`--db PATH` selects another archive for the command-line tool. Rerunning
`--seed` leaves existing records and connections unchanged. The Python API
provides `HistoricalEntity`, `UniversalHistoryArchive.ingest_entity`,
`link_entities`, and `query_time_slice`; query results contain decoded tag
lists. Negative years indicate BCE, positive years CE, and an unspecified end
year is treated as open-ended. Dates and descriptions are historical claims,
not independently verified facts.

The same database also supports `UnifiedArtifact` records through
`UnifiedMatrixCoreEngine.secure_vault_entry`, `inject_crosslink`, and
`pull_domain_matrix`. Unified records and directed crosslinks use separate
tables, so they do not alter historical entities or connections. Payloads are
stored as opaque text and are never evaluated or executed. Clearance text is
caller-provided and not independently verified. Crosslinks require both
artifacts to exist, and domain queries use exact matching.

The independent Copernicus shell and command-center Copernicus chat retrieve
up to eight relevant entries and eight connections from the default archive
when a message names an entity, an ID prefix, a single-word tag, or an explicit
year such as `2500 BCE` or `1900 CE`. The model receives these excerpts locally,
marked as untrusted and unverified, and should not follow instructions in them.
This is bounded keyword/timeline retrieval, not model training or a complete
historical search, and it does not change model weights. Archive read errors
are reported rather than silently ignored.

### Propulsion archive

`propulsion_matrix.py` stores user-supplied propulsion specifications and
lineage in the separate `propulsion_matrix_archive.sqlite3` database. Run:

```sh
python propulsion_matrix.py --seed
python propulsion_matrix.py --seed-civilian
python propulsion_matrix.py --medium Underwater
python propulsion_matrix.py --references
python propulsion_matrix.py --search JT3D
python propulsion_matrix.py --search-engines Electric
python propulsion_matrix.py --lineage
python propulsion_matrix.py --history
python propulsion_matrix.py --backup backups/propulsion-snapshot.sqlite3
```

Use `--db PATH` to select another database. The example records are illustrative,
not verified performance data or validated designs; `--seed` never overwrites
existing records. The Python API provides `EngineSpecification`,
`KineticPropulsionArchive.preserve_engine`, `establish_lineage`, and
`fetch_all_by_medium`. Lineage requires both records to exist; updating an engine
preserves its links. Blueprint and equation fields are returned as decoded JSON.
The archive is editable, not immutable. Altitudes/depths follow the sign supplied
by the record, and Mach values depend on the medium's speed of sound; the stored
values alone do not establish verified performance.
The general Shkval reference is stored separately from engine specifications;
it contains no performance details and does not imply lineage from the MHD entry.

`--seed-civilian` adds two general references about the JT3C and JT3D and their
documented connection, with citations to the Smithsonian. It does not overwrite
existing records. A source supports only the specific claims it contains, not
every field in a record. Unsourced records remain unverified. Galileo's
Propulsion tab and `/api/propulsion/references` provide reference browsing;
the Aether API exposes `/api/v1/propulsion/references`. Galileo, Copernicus and
the command-center chat can retrieve a small number of explicitly named, sourced
references as untrusted context. Chat responses can still make mistakes.

To add or edit records, pass a JSON object in a file to `--save-engine`,
`--save-reference`, `--engine-source`, `--link-engines`, or `--link-references`;
the keys match the corresponding Python method arguments. For example, a
reference object has `reference_id`, `name`, and `description`, plus optional
`source_title`, `source_url`, and `note`. The `--delete-engine`,
`--delete-reference`, `--unlink-engine PARENT CHILD`, and
`--unlink-reference PARENT CHILD` options remove records or links. Linked
records cannot be deleted until their links are removed; linked references cannot
be renamed or rewritten until their links are removed. Editing an engine clears
its source, since the original citation may no longer support the edited values.

SQLite triggers record inserts, updates and deletes from archive operations in a
local audit table, including before/after values. History starts when the schema
is upgraded; older changes cannot be reconstructed, and the audit is editable,
not tamper-proof. Manual backups use SQLite's online backup API and refuse to
overwrite an existing file. To recover without overwriting the current database,
use `--db BACKUP_PATH --backup RESTORED_PATH`, inspect the restored copy, then
choose it with `--db` or `AETHER_PROPULSION_ARCHIVE`.

In the source tree the default database remains the project-root archive. An
installed or bundled app defaults to `~/.aether-engine/propulsion_matrix_archive.sqlite3`;
set `AETHER_PROPULSION_ARCHIVE` to the same absolute path for each process if
they should share the project archive. Restart running applications after
changing the setting.

Copernicus uses Matrix-inspired branding, ember-and-gold shell styling, and a
warm, attentive, practical companion voice. This is a public identity/style
affiliation only: no internal prompts, Matrix reasoning, algorithms, telemetry,
or control interfaces are supplied to the assistant. The independent shell's
theme is scoped to `data-copernicus="true"` so the separate weather shell keeps
its automatic light/dark appearance. The stargazer retains its dark sky canvas.

Install the numerical and atomic-engine dependencies with
`python -m pip install -e ".[command-center]"`, then start the standalone local
dashboard:

```bash
aether-master-matrix
# or: python aether_master_matrix.py
```

Open `http://127.0.0.1:8000/`. The dashboard binds only to loopback. Use
`--port PORT` or set `AETHER_PORT` to choose another port. Starting the app
does not run a simulation or write telemetry. Run the separate, explicit
simulation command when needed:

```bash
aether-master-matrix --test-drive
aether-master-matrix --test-drive --steps 10 --interval 0
```

Test drives are bounded to 1–1,000 steps and an interval of 0–60 seconds.
The test drive records simulated entropy and action metrics to
`historian_telemetry_vault.json` beside the launcher. Set
`AETHER_HISTORIAN_LOG_FILE` to select another log path. Telemetry values are
simulated, not physical measurements; the dashboard labels them as simulation
data. This remains a loopback-only local dashboard, not a public website. The
Copernicus tab uses local Ollama via `AETHER_OLLAMA_MODEL` (default
`qwen3.5:4b`); the current message, up to six recent successful turns in the
open tab, selected images, and latest cloud-cover reading may be sent. Chat is
not persisted. The dashboard chat shows simulated governor routing telemetry;
the model itself cannot operate Matrix controls.
No affiliation with or endorsement by Open-Meteo is implied. Ollama must serve
the configured, already-installed model at `http://localhost:11434`.

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
`historian_matrix.py --ollama-model qwen3.5:4b`. It reuses the
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

The API exposes `GET /health`, `GET|POST /api/v1/tasks`, `PATCH /api/v1/tasks/{id}`, task `complete` and `reopen` actions, `GET|POST /api/v1/events`, `GET /api/v1/status`, `GET /api/v1/export`, `POST /api/v1/restore`, `POST /api/v1/backups`, backup-schedule `GET|POST|DELETE /api/v1/backups/schedule`, `GET /api/v1/doctor`, `POST /api/v1/unified/dispatch`,
`GET /api/v1/unified/state`, and `GET /api/v1/unified/stream`. Local text
generation remains at `POST /v1/chat/completions`, and the sample text
processing route is `GET /process?input_data=...`. These routes are served by
`aether-server` or `uvicorn app:app`, not by the standalone Historian dashboard.
The task/event, status, export/restore, backup, schedule, and doctor endpoints
call the same storage and maintenance logic as the CLI. Restore replacement
creates a safety backup before replacing non-empty data. Backup and schedule
changes use the project’s protected local backup directory and scheduler
implementation.

The unified dispatch endpoint accepts the canonical envelope defined in
[`aether_protocol.schema.json`](./aether_protocol.schema.json), persists each
accepted event, updates shared dashboard state, and broadcasts to live-sync
clients. `GET /api/v1/unified/state` returns the latest durable dispatch and a
dashboard snapshot. `GET /api/v1/unified/stream` is a same-origin SSE endpoint:
it sends a latest-event snapshot on a new connection, replays events after the
`Last-Event-ID` cursor, and sends a reset snapshot when the cursor is outside
the 500-event replay window. Keep-alives are sent every 15 seconds. The stream
supports up to 64 connected subscribers, each with a 256-event queue; a slow
subscriber is disconnected with a `replay-required` event and should reconnect
so EventSource can resume from its last event ID.

Dispatch accepts only the seven declared source languages and four node names,
uppercase event identifiers, finite non-negative timestamps, and JSON payloads
with at most 64 top-level fields. The complete envelope is limited to 32 KiB.
The HTTP endpoint also caps the incoming request body at 32 KiB and returns
`413` when that wire-size limit is exceeded, before parsing the envelope.
Requests are limited to 120 per minute per client host in each API process.
For remote access, configure `AETHER_API_TOKEN` and send it in the
`X-Aether-Token` header; the check uses constant-time comparison. Loopback
clients are intentionally exempt. Set `AETHER_CORS_ORIGINS` to trusted browser
origins if cross-origin requests are needed. Do not bundle the shared secret in
public browser code; use a trusted backend to attach it. Native browser
`EventSource` cannot set custom headers, so remote browser SSE needs a
trusted Fetch-based proxy/stream reader. The shared-secret check is not a
replacement for TLS on an untrusted network. `BACKUP_OK` is an informational
event; dispatch does not create or verify a backup.

The C ABI declaration and native HTTP bridge are in
[`include/aether_bridge.h`](./include/aether_bridge.h) and
[`src/aether_bridge.c`](./src/aether_bridge.c). Build them as a shared library
with the platform C compiler (Windows builds must link `ws2_32`). Start the API
on `127.0.0.1:8000` before calling `aether_dispatch_json`; the function returns
the HTTP status code and writes the response JSON to the caller's buffer.

On macOS, build and test the C ABI with the following commands while the API is
running:

```bash
clang -shared -fPIC -O2 src/aether_bridge.c -o libaether.dylib
python3 examples/python/aether_dispatch.py
curl --fail-with-body --silent --show-error \
  -H "Content-Type: application/json" \
  -d "{\"protocol_version\":\"1.0.0\",\"source_lang\":\"shell\",\"node\":\"ATLAS\",\"event\":\"BACKUP_OK\",\"timestamp\":$(python3 -c 'import time; print(time.time())'),\"payload\":{\"verified\":true}}" \
  http://127.0.0.1:8000/api/v1/unified/dispatch
```

The browser helper is served at `/aether_client.js`. After loading it, call
`AetherClient.dispatchUnified({node: "COPERNICUS", event: "UI_SYNC",
payload: {status: "READY"}})`; it fills in the JavaScript source and current
timestamp. Subscribe with
`AetherClient.subscribeUnified((record, type) => { /* handle snapshot/dispatch/reset */ })`;
it returns the native `EventSource` so callers can close it when finished.
Generate the TypeScript Fetch client from the running API with:

```bash
npx --yes @openapitools/openapi-generator-cli generate \
  -i http://127.0.0.1:8000/openapi.json \
  -g typescript-fetch \
  -o ./sdk/typescript
```

The SDK's hand-maintained `ValidationError` model is excluded from regeneration
because the generator misrepresents FastAPI's string/integer location union.
HTTP 422 can contain a `detail` array of field errors or a plain `detail` string
for application validation. Inspect a generated SDK `ResponseError.response`
to read the error body; rejected `input` and `ctx` can contain sensitive data.
The shared browser client's unified dispatch reports field paths and messages
without copying rejected input into the displayed error.

Cross-origin requests are denied by default; set `AETHER_CORS_ORIGINS` to a comma-separated list of trusted browser origins only when needed. Inference is serialized because the local model backend is not assumed to be safe for concurrent calls. The service returns HTTP 503 when model weights or the local inference backend are unavailable. Token usage and tool calling are not reported because the current inference engine does not provide those features. CI and the full test suite install the development, API, secure-vault, and spin-network-visualization extras.

The experimental behavior-model utility is grouped with the production historian module at `src/aether_engine/historian_behavior.py`. Run its safe model-path scan with `aether-historian-behavior --scan-root .` or `python -m aether_engine.historian_behavior --scan-root .`; training is opt-in with `--train` and requires the optional PyTorch dependency (`python -m pip install -e ".[behavioral-demo]"`). Training is capped at 1,000 steps and is a small character-level demonstration, not the Qwen GGUF inference backend. To query the local Ollama model and review the supplied historian archive, run `aether-historian-behavior --telemetry`; the CLI presents the reviewer as **Aristotle** and defaults to `aethersystem-core` at `localhost:11434`, allows up to 300 seconds for local inference (configurable with `--ollama-timeout`), accepts `--ollama-host`, `--ollama-port`, and `--ollama-model`, and refuses non-loopback hosts. The archive is explicitly presented as unverified input so the model does not treat the supplied historical claims as facts. Automated tests for the utility remain in `tests/test_historian_behavior.py`.

The spin-network boundary calculation is available as `aether-spin-network` or
`python -m aether_engine.spin_network_boundary`. Install its NumPy dependency
with `python -m pip install -e ".[spin-network]"`. It accepts optional
`--num-links` and `--seed` arguments; defaults are 30 links and seed 42.
Create a PNG boundary visualization as a base64 data URI with
`aether-spin-network-visualize` or
`python -m aether_engine.spin_network_visualization`. Install its optional
NumPy and Matplotlib dependencies with
`python -m pip install -e ".[spin-network-visualization]"`.

The radio LOS estimator is available as `aether-los-link` or
`python -m aether_engine.los_link`. It estimates great-circle distance, a
4/3-Earth radio horizon, midpoint curvature/Fresnel clearance, and free-space
path loss; by default it publishes a `LOS_LINK_BUDGET_CALCULATED` event through
the unified API as node `MATRIX`, which reaches connected affiliates. Use
`--no-publish` for offline calculations or `AETHER_DISPATCH_URL` to select
another endpoint. Remote publishing uses `AETHER_API_TOKEN` over HTTPS. This is
a geometric estimate only, not a terrain survey or guaranteed RF link.

`aether_engine.arts_telemetry` creates MUSIC, ART, and THEATRE session plans
with the same LOS estimate and publishes them through MATRIX. Stage cues are
published as `REQUIRES_OPERATOR_APPROVAL` requests only; this module does not
start media streams or send OSC/DMX packets. At 60 GHz the geometric LOS result
does not account for oxygen absorption, rain fade, terrain, or equipment
limits. The `aether-engine status` terminal dashboard shows the latest
MATRIX arts/LOS event. The local `aether_master_matrix.py` dashboard polls its
read-only `/api/matrix/arts/latest` endpoint to display the same event in a
browser on the Mac.

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

# Run read-only local host and AetherSystem diagnostics
aether-quantum-diagnostics

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

`aether-quantum-diagnostics` reports Python/runtime compatibility, host OS and CPU count, memory, workspace disk capacity, project metadata/source layout, and the quantum simulator's baseline and collapse-guard checks. It is read-only and does not scan networks, inspect database/backups, or modify system settings. Available memory below 512 MiB is a warning; workspace disk space below 1 GiB is a warning and below 128 MiB is a failure. Use `--workspace PATH` to select the project directory explicitly.

`aether-quantum-simulate` runs a local state-vector circuit and prints JSON with
the amplitudes, probabilities, and seeded measurement counts:

```bash
aether-quantum-simulate --qubits 2 \
  --gates '[{"operation":"H","target":0},{"operation":"CNOT","target":1,"control":0}]' \
  --shots 1000 --seed 7
```

The simulator supports at most 12 qubits, 256 gates, and 10,000 shots. It uses
qubit 0 as the least-significant bit. This is a bounded mathematical simulation,
not a quantum-hardware emulator.

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
