# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Windows desktop app ("Árbitros") for managing football referees: availability, leagues/short tournaments, match days, WhatsApp rosters, match reports (cédulas) and payments. Single user, local SQLite, offline-first. The UI, domain names, code identifiers and user-facing text are in **Spanish** — keep it that way. Full agreed requirements and phase roadmap: `docs/requisitos.md` (phase 1 done; phases 2–6 pending).

## Commands

```powershell
# Setup (use `python -m pip`; pip.exe is blocked by Windows App Control on this machine)
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"

# Run the app (real data in %APPDATA%\Arbitros) — or double-click iniciar.bat
$env:PYTHONPATH="src"; .\.venv\Scripts\python -m arbitros
# Run against throwaway data
$env:ARBITROS_DATA_DIR="$PWD\datos_dev"; $env:PYTHONPATH="src"; .\.venv\Scripts\python -m arbitros

# Tests
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m pytest tests/test_arbitros.py::test_busqueda
```

**SQLAlchemy must be installed as pure Python**: Windows App Control blocks its compiled `.pyd` extensions (`DLL load failed ... Control de aplicaciones`). Install/reinstall with `$env:DISABLE_SQLALCHEMY_CEXT="1"; python -m pip install --no-binary sqlalchemy --force-reinstall --no-deps sqlalchemy==<ver>`. Expect the same issue for other packages with native extensions; this will also matter for the phase 6 packaged `.exe` (unsigned binaries).

The first app launch downloads the Flet desktop client (needs internet once).

## Architecture

Layering is strict: `ui/` → `services/` → `db/`. Views never touch SQLAlchemy sessions directly; all business rules and validation live in services so they are testable without a UI.

- `config.py` — `Rutas`: data dir (`%APPDATA%\Arbitros`, overridable via `ARBITROS_DATA_DIR`) holding `arbitros.db`, `documentos/`, `respaldos/`, `arbitros.log`. Data lives outside the install dir so updates never touch it.
- `db/database.py` — `Database` wraps engine + `sesion()` context manager (commit/rollback). Sessions use `expire_on_commit=False`, so services return detached ORM objects that the UI reads freely (don't lazy-load relationships from the UI).
- `db/migrar.py` + `db/migrations/` — Alembic configured in code (no `alembic.ini`); `migrar()` runs `upgrade head` on every startup. **Any model change requires a new migration** in `db/migrations/versions/` (users have existing DBs). Generate one with `command.revision(configuracion_alembic(db), message=..., autogenerate=True, rev_id="000N")` against a temp DB that is at head; `render_as_batch=True` is set for SQLite.
- `services/` — one class per domain, constructed with `Database`. Validation errors raise `ErrorValidacion(mensaje, campos={campo: msg})`; the UI maps `campos` onto `TextField.error` via `ui.comunes.mostrar_errores`.
- `services/respaldos.py` — ZIP backups (`manifest.json` + SQLite backup-API copy + `documentos/`). Restore validates ZIP paths and that the backup's Alembic revision is known, makes a safety backup, then `Database.cerrar()` and replaces files; caller re-runs `migrar()`.
- `ui/app.py` — `App` is the single object passed to every view: page, services, logged-in `usuario`, and Flet services (`FilePicker`, `Clipboard`), which must be created inside `main()` to auto-register with the page. Screen flow: first-run setup → login → `Shell`.
- `ui/shell.py` — NavigationRail + content area. Modules are declared in `SECCIONES`; a section with `construir=None` renders a "Próximamente (fase N)" placeholder. To add a module: create `ui/vistas/<modulo>.py` exposing `construir(app, shell) -> ft.Control` and set it on its `Seccion`.
- Role checks (`app.es_admin`) are enforced in the UI (Consulta users get read-only views); services trust the caller.

## Flet 1.0 notes

The project pins Flet 1.0.x, whose API differs from older tutorials: `ft.run(main)`, `ft.Colors`/`ft.Icons`, `ft.Button`/`ft.FilledButton` (no `ElevatedButton`), dialogs and snackbars via `page.show_dialog()` / `page.pop_dialog()`, `TextField(error=..., helper=...)`, `Dropdown(on_select=...)`, `ft.Padding.symmetric(...)`, `ft.Alignment.CENTER`, and services like `FilePicker` use `await` methods (`pick_files`, `get_directory_path`). Check signatures in `.venv/Lib/site-packages/flet/controls/` when unsure.

`tests/test_ui_smoke.py` builds every screen and dialog against a fake page — it catches invalid Flet parameters without opening a window. Keep it updated when adding views.

## Domain conventions

- Phone numbers are stored normalized (digits, optional leading `+`); 10-digit numbers get `LADA_PAIS` (52, Mexico) prepended for WhatsApp links.
- Referee search is done in Python and is accent/case-insensitive (`sin_acentos`).
- Referees are deactivated, never deleted (history must be preserved).
