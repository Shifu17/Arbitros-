# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Windows desktop app ("Árbitros") for managing football referees: availability, leagues/short tournaments, match days, WhatsApp rosters, match reports (cédulas) and payments. Single user, local SQLite, offline-first. The UI, domain names, code identifiers and user-facing text are in **Spanish** — keep it that way. Full agreed requirements and phase roadmap: `docs/requisitos.md` (phases 1–5 done; 6 pending). Organization: Colegio de Árbitros de Coahuila (`config.ORGANIZACION`). Bump `__version__` in `src/arbitros/__init__.py` and `pyproject.toml` together at the end of each phase.

## Commands

```powershell
# Setup
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

Windows App Control (Smart App Control) was enabled on the dev machine during phase 1 and blocked unsigned binaries (`pip.exe`, SQLAlchemy's `.pyd`), so the venv has a pure-Python SQLAlchemy build; the user has since disabled it. If `DLL load failed ... Control de aplicaciones` reappears, reinstall with `$env:DISABLE_SQLALCHEMY_CEXT="1"; python -m pip install --no-binary sqlalchemy --force-reinstall --no-deps sqlalchemy==<ver>`. Keep this in mind for the phase 6 unsigned `.exe` on end-user machines.

The first app launch downloads the Flet desktop client (needs internet once).

## Architecture

Layering is strict: `ui/` → `services/` → `db/`. Views never touch SQLAlchemy sessions directly; all business rules and validation live in services so they are testable without a UI.

- `config.py` — `Rutas`: data dir (`%APPDATA%\Arbitros`, overridable via `ARBITROS_DATA_DIR`) holding `arbitros.db`, `documentos/`, `respaldos/`, `arbitros.log`. Data lives outside the install dir so updates never touch it.
- `db/database.py` — `Database` wraps engine + `sesion()` context manager (commit/rollback). Sessions use `expire_on_commit=False`, so services return detached ORM objects that the UI reads freely (don't lazy-load relationships from the UI).
- `db/migrar.py` + `db/migrations/` — Alembic configured in code (no `alembic.ini`); `migrar()` runs `upgrade head` on every startup, and `main.py` makes an `antes_de_actualizar_*` backup first when `necesita_migrar()` is true. `migrar()` runs all pending migrations in one transaction with `PRAGMA foreign_keys=OFF` (batch mode recreates tables, which fails on referenced tables with data) and checks `foreign_key_check` before committing. `Database` uses SQLAlchemy's pysqlite recipe (`isolation_level=None` + explicit `BEGIN`) so DDL is transactional — a failed migration rolls back fully. Test migrations against DBs **with data** (`tests/test_migraciones.py`). **Any model change requires a new migration** in `db/migrations/versions/` (users have existing DBs). Generate one with `command.revision(configuracion_alembic(db), message=..., autogenerate=True, rev_id="000N")` against a temp DB upgraded to the previous head (use a Windows path for the temp DB, not `/c/...`); `render_as_batch=True` is set for SQLite.
- `services/` — one class per domain, constructed with `Database`. Validation errors raise `ErrorValidacion(mensaje, campos={campo: msg})`; the UI maps `campos` onto `TextField.error` via `ui.comunes.mostrar_errores` (Dropdowns use `error_text`). Non-blocking warnings raise `AvisosPendientes(avisos)`; the UI shows them (`comunes.mostrar_avisos`) and retries with `forzar=True` ("Guardar de todas formas").
- `services/ligas.py` — `LigaService` plus `Catalogo`, a shared implementation for a league's `equipos` and `campos` (`app.ligas.equipos`, `app.ligas.campos`). A "torneo" is a `Liga` with `tipo="torneo"` whose `Jornada` rows are its days; `JornadaService` renumbers torneo days by date (two-step to dodge the `(liga_id, numero)` unique constraint).
- `Categoria` = sub-liga (Veteranos, Premier A…). Equipos and partidos may carry `categoria_id`; when a liga has active categorías a partido must have one. Effective defaults go through `LigaService.posiciones_para()` and `tarifa_para()` (categoría overrides → liga). `TarifaCategoria` rows exist only when a categoría has its own tarifas.
- `services/jornadas.py` — jornadas and partidos. `Partido.posiciones` is a CSV of keys from `models.POSICIONES`, copied from the league default and overridable per match. `Partido` relationships are `lazy="joined"` so detached objects expose `local/visitante/campo` names.
- Partido `estado` in `ESTADOS_SIN_JUEGO` (cancelado/suspendido) means it is ignored by every conflict check and can't receive referees; `motivo_estado` holds the reason.
- `services/disponibilidad.py` — one `Disponibilidad` row per árbitro/día (no row = "sin registrar").
- `services/asignaciones.py` — `Asignacion` (partido, posición, árbitro); phase 5 payments will hang off it. `_evaluar()` is the single source of conflict rules (availability, time window, overlap using configurable match duration + rest stored in `Configuracion`), used by `candidatos()`, `asignar()` and `revisar_jornada()` (re-checks existing assignments after edits). Overlaps are checked across all ligas for the same day. Removing a position from a partido deletes its assignment.
- `services/rol.py` — builds a `RolJornada` (resolved names/positions) used by both the WhatsApp text (`*bold*`, `_italic_`, `~strike~`) and `rol_imagen.py` (Pillow, two-pass measure/draw, Segoe UI from `%WINDIR%\Fonts`, no emoji in images). `publicar()` stores a JSON snapshot in `Jornada.rol_publicado`; `cambios()` diffs the current state against it.
- `services/pagos.py` — per-assignment balance: tarifa − `pagado_campo` − `pagado_despues`. Effective tarifa comes from `tarifa_para()` until money is recorded, then it is frozen in `Asignacion.tarifa_centavos`. A `Pago` liquidates the full balance of selected assignments (`deshacer_pago` reverts). `services/cedulas.py` copies files into `documentos/cedulas/liga_<id>/jornada_<id>/` (stored as relative paths, so backups include them). `services/reportes.py` exports a multi-sheet Excel with openpyxl.
- `ui/tema.py` — brand theme (black/yellow/red from the logo in `src/arbitros/assets/`). Status colors are fixed constants (`EXITO_*`, `AVISO_*`, `PELIGRO_*`), deliberately not `ft.Colors.PRIMARY*`/`ERROR*`, because the brand primary is red. Use them for any "ok / warning / missing" state.
- Money is always integer centavos (`services/dinero.py`).
- Name comparisons, uniqueness and sorting are accent/case-insensitive and done in Python via `services/texto.sin_acentos` (SQLite's `lower()`/collation don't handle accents).
- `services/respaldos.py` — ZIP backups (`manifest.json` + SQLite backup-API copy + `documentos/`). Restore validates ZIP paths and that the backup's Alembic revision is known, makes a safety backup, then `Database.cerrar()` and replaces files; caller re-runs `migrar()`.
- `ui/app.py` — `App` is the single object passed to every view: page, services, logged-in `usuario`, and Flet services (`FilePicker`, `Clipboard`), which must be created inside `main()` to auto-register with the page. Screen flow: first-run setup → login → `Shell`.
- `app.seleccion` remembers the selected liga/jornada across sections (e.g. "Ver jornadas" from a liga opens that liga in Jornadas).
- `ui/comunes.py` — shared widgets: `CampoFecha` (dd/mm/aaaa text + DatePicker), `selector_hora`, `avisos_panel`, confirmation/snackbar helpers.
- `ui/shell.py` — NavigationRail + content area. Modules are declared in `SECCIONES`; a section with `construir=None` renders a "Próximamente (fase N)" placeholder. To add a module: create `ui/vistas/<modulo>.py` exposing `construir(app, shell) -> ft.Control` and set it on its `Seccion`.
- Role checks (`app.es_admin`) are enforced in the UI (Consulta users get read-only views); services trust the caller.

## Flet 1.0 notes

The project pins Flet 1.0.x, whose API differs from older tutorials: `ft.run(main)`, `ft.Colors`/`ft.Icons`, `ft.Button`/`ft.FilledButton` (no `ElevatedButton`), dialogs and snackbars via `page.show_dialog()` / `page.pop_dialog()`, `TextField(error=..., helper=...)`, `Dropdown(on_select=...)`, `ft.Padding.symmetric(...)`, `ft.Alignment.CENTER`, and services like `FilePicker` use `await` methods (`pick_files`, `get_directory_path`). Check signatures in `.venv/Lib/site-packages/flet/controls/` when unsure.

`tests/test_ui_smoke.py` builds every screen and dialog against a fake page — it catches invalid Flet parameters without opening a window. Keep it updated when adding views. It does **not** catch layout problems (e.g. a Row of buttons squashing a title into a vertical column of letters): the default window is 1240×800 with a 220 px menu, so keep tables to ~5 columns or wrap them in a horizontally scrollable Row, and put action buttons in their own `wrap=True` row.

## Domain conventions

- Phone numbers are stored normalized (digits, optional leading `+`); 10-digit numbers get `LADA_PAIS` (52, Mexico) prepended for WhatsApp links.
- Referees and leagues are deactivated/archived, never deleted (history must be preserved). Equipos/campos can only be deleted while no partido references them.
