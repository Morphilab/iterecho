# IterEcho — Procesador de archivos seguro

[English](README.md) | **Español**

[![CI](https://github.com/Morphilab/iterecho/actions/workflows/test.yml/badge.svg)](https://github.com/Morphilab/iterecho/actions/workflows/test.yml)
[![Versiones de Python](https://img.shields.io/badge/python-3.8%20|%203.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13%20|%203.14-blue)](#versiones-de-python-compatibles)
[![Licencia: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Estilo: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy strict](https://img.shields.io/badge/mypy-strict-blue)](https://mypy-lang.org)
[![Seguridad: bandit clean](https://img.shields.io/badge/security-bandit%20clean-brightgreen)](https://github.com/PyCQA/bandit)

IterEcho es una herramienta CLI de Python 3.8+ centrada en seguridad que
**copia, concatena o fragmenta** un árbol de archivos. Está pensada para
administradores de sistemas y desarrolladores que necesitan consolidar logs,
empaquetar documentación o dividir archivos grandes en piezas de tamaño
limitado, sin incluir scripts por accidente ni filtrar datos mediante el
recorrido de enlaces simbólicos.

## ¿Por qué IterEcho?

- **Seguridad desde el diseño.** Los archivos de origen se abren con
  `O_NOFOLLOW` y se validan con `fstat` sobre el descriptor abierto, lo que
  elimina la ventana TOCTOU entre validación y lectura. El recorrido de rutas
  se comprueba con `path.resolve()` + `relative_to(base)` en
  `SecurityEngine.is_within_base`. Las extensiones críticas solicitadas
  (`.exe`, `.bat`, `.dll`, `.ps1`, `.vbs`, …) se rechazan siempre (el filtro
  se aplica a la extensión de la ruta buscada); las extensiones de
  advertencia (`.py`, `.sh`, `.js`, …) requieren `--unsafe` explícito.
- **Tres modos, una herramienta.** `copy` (con saneamiento de nombres),
  `concatenate` (con cabeceras por archivo) y `chunk` (salida dividida por
  tamaño).
- **Doble interfaz.** Una CLI basada en Typer con opciones globales al estilo
  de Git y una TUI interactiva basada en Rich.
- **Streaming.** Los archivos se leen en bloques de 1 MiB, sin cargar el
  archivo completo en memoria.
- **Seguridad en concurrencia.** El bloqueo advisory `fcntl.lockf` (POSIX)
  evita que dos instancias sobrescriban el mismo directorio de salida. El
  bloqueo se libera al terminar el procesamiento y un hook `atexit` lo limpia
  en una salida normal del intérprete. Tras un `SIGKILL`, el kernel libera el
  bloqueo advisory y la siguiente ejecución reutiliza el archivo de bloqueo;
  en Windows, donde no existe `fcntl`, el respaldo `O_EXCL` + comprobación de
  PID inspecciona el bloqueo residual y lo elimina si su PID ya no existe.
- **Bien cubierto.** Suites unitarias, de integración, de CLI (CliRunner), de
  TUI (mock de stdin) y de casos límite de seguridad.

## Divulgación de IA

Este proyecto se desarrolló con asistencia de herramientas de inteligencia
artificial. Dada la naturaleza automatizada de algunos componentes, se
recomienda revisar y probar el código de forma independiente antes de
integrarlo en otros sistemas.

## Índice

- [Instalación](#instalación)
- [Inicio rápido](#inicio-rápido)
- [Modos](#modos)
- [Referencia de la línea de comandos](#referencia-de-la-línea-de-comandos)
- [Seguridad](#seguridad)
- [Arquitectura](#arquitectura)
- [Desarrollo](#desarrollo)
- [Hoja de ruta](#hoja-de-ruta)
- [Pruebas](#pruebas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

## Instalación

```bash
git clone https://github.com/Morphilab/iterecho.git
cd iterecho
uv sync --extra dev
```

Alternativa con pip (requiere `python3-venv` en el sistema):

```bash
pip install -e ".[dev]"
```

O, cuando esté publicado, simplemente:

```bash
pip install iterecho
```

## Inicio rápido

```bash
# Mostrar la versión
iterecho --version

# Modo interactivo (recomendado para el primer uso)
iterecho interactive

# Copiar archivos con saneamiento de nombres
iterecho --extensions .txt,.log --base-dir ./my-files --output-dir ./output copy

# Concatenar archivos (con cabeceras en la salida)
iterecho --extensions .txt --base-dir ./data concatenate

# Dividir en fragmentos de tamaño limitado
iterecho --extensions .txt --base-dir ./logs chunk --chunk-size 50M
```

Las opciones globales van antes del subcomando; las específicas del subcomando,
después:

```bash
iterecho --verbose --unsafe --extensions .py,.txt copy --follow-symlinks
iterecho --overwrite --output-dir ./out chunk --chunk-size 10M
```

## Modos

### `copy`

Copia archivos de `--base-dir` a `--output-dir` (por defecto hace una copia
saneada en el mismo lugar). El nombre de destino se reconstruye a partir del
nombre base saneado más `--output-extension` (`.txt` por defecto), así que
`notes.md` queda como `notes.txt`; en una copia en el mismo lugar, el archivo
original permanece y la copia renombrada se crea junto a él. El saneamiento
sustituye caracteres de control, bytes NUL y caracteres Unicode de suplantación
por `_`; antepone `_` a los nombres que empiezan por `-` y a los nombres
reservados de Windows (`CON`, `NUL`, …); elimina los puntos finales; y trunca a
200 caracteres conservando la extensión. Se mantiene la estructura de
subdirectorios.

```bash
iterecho --base-dir ./src --output-dir ./dst --extensions .md copy
```

### `concatenate`

Combina todos los archivos coincidentes en una sola salida con una cabecera por
archivo:

```
================================================================================
FILE: logs/2024-01-01.log (12,345 bytes)
================================================================================

...contenido del archivo...

================================================================================
FILE: logs/2024-01-02.log (15,678 bytes)
================================================================================
```

```bash
iterecho --base-dir ./logs --extensions .log concatenate --output-prefix combined
# -> ./logs/combined.txt   (se escribe en --output-dir, o en --base-dir si no se indica)
```

`--output-file` se resuelve dentro de `--output-dir`; las rutas que escapan de
ese directorio se rechazan.

### `chunk`

Divide el contenido combinado en varios archivos. La comprobación de tamaño
compara el fragmento en curso con el siguiente archivo **más su cabecera**, y
abre un fragmento nuevo cuando se superaría `--chunk-size`, por lo que un
fragmento puede quedar ligeramente por encima del límite. Un archivo mayor que
`--chunk-size` se escribe en un fragmento propio, con una advertencia.

```bash
iterecho --base-dir ./logs --extensions .log chunk --chunk-size 50M
# -> ./logs/chunk_001.txt, ./logs/chunk_002.txt, ...
```

Los nombres de fragmento siguen `{prefix}_{NNN}{extension}` — `chunk_001.txt`
por defecto (ver `--output-prefix` y `--output-extension` más abajo).

> **Código de salida (todos los modos):** una entrada que falla durante el
> procesamiento (validación o E/S) se registra y se omite; la ejecución continúa
> y aun así termina con `0`, de modo que una salida puede quedar incompleta sin
> un código distinto de cero. Los fallos que detienen la ejecución terminan con
> `1`: salida existente de `concatenate`/`chunk` sin `--overwrite`, directorio de
> salida bloqueado o `--chunk-size` no positivo. `copy` nunca falla por un
> destino existente: lo omite (log de depuración) salvo que se use
> `--overwrite`. Revisa el log, no solo el código de salida.

## Referencia de la línea de comandos

Las opciones globales se aplican a todos los subcomandos y van **antes** del
subcomando:

| Opción | Valor por defecto | Descripción |
| --- | --- | --- |
| `--version` | — | Muestra la versión y sale |
| `--extensions` | `.txt` | Extensiones separadas por comas (p. ej. `.txt,.log`) |
| `--base-dir` | directorio actual | Directorio base para la búsqueda |
| `--output-dir` | `--base-dir` | Directorio de salida |
| `--output-extension` | `.txt` | Extensión de los archivos generados |
| `--recursive / --no-recursive` | recursivo | Busca en subdirectorios |
| `--name-filter` | ninguno | Subcadena que debe aparecer en el nombre |
| `--max-file-size` | `100M` | Omite archivos mayores (p. ej. `100M`, `1G`) |
| `--unsafe` | desactivado | Permite extensiones de advertencia (`.py`, `.sh`, …) |
| `--overwrite` | desactivado | Sobrescribe archivos de salida existentes |
| `--verbose / -v` | desactivado | Activa el log DEBUG |
| `--quiet / -q` | desactivado | Silencia todo salvo advertencias y errores |
| `--dry-run` | desactivado | Muestra lo que se procesaría sin escribir |

Las opciones específicas de cada subcomando van **después** del subcomando:

| Subcomando | Opción | Valor por defecto | Descripción |
| --- | --- | --- | --- |
| `copy` | `--follow-symlinks` | desactivado | Sigue enlaces simbólicos |
| `concatenate` | `--output-file` | ninguno | Nombre del archivo de salida (anula `--output-prefix`) |
| `concatenate` | `--output-prefix` | `concatenated` | Prefijo del nombre del archivo de salida |
| `chunk` | `--chunk-size` | `50M` | Tamaño máximo por fragmento (p. ej. `10M`, `1G`) |
| `chunk` | `--output-prefix` | `chunk` | Prefijo de los nombres de fragmento |
| `chunk` | `--follow-symlinks` | desactivado | Sigue enlaces simbólicos |
| `interactive` | — | — | Modo TUI (ignora las opciones globales) |

## Seguridad

El modelo de seguridad de IterEcho está documentado en detalle en
[`SECURITY.md`](SECURITY.md). Resumen:

| Amenaza | Mitigación |
| --- | --- |
| Recorrido de rutas con `..` o enlaces simbólicos | `path.resolve()` + `relative_to(base)` |
| TOCTOU entre validación y E/S | `os.open(O_NOFOLLOW)` + `os.fstat` para archivos regulares; los destinos de enlaces simbólicos se resuelven y revalidan antes de abrirlos |
| Escape por cadena de enlaces simbólicos | El destino resuelto se revalida contra la base |
| Condiciones de carrera entre procesos | Bloqueo advisory `fcntl.lockf` (POSIX) |
| Inyección en nombres de archivo | `sanitize_filename` elimina caracteres de control, NUL, BOM y ZWJ |
| Suplantación visual con Unicode | Normalización NFC; caracteres de ancho cero y de dirección RTL sustituidos |
| Contrabando de ejecutables | Las `CRITICAL_EXTENSIONS` solicitadas (44 entradas) se rechazan; el filtro se aplica a la extensión de la ruta buscada |
| Procesamiento de scripts | Las `WARNING_EXTENSIONS` solicitadas se bloquean salvo `--unsafe` |
| Fugas de descriptores en excepciones | `try/finally` por entrada; los archivos de fragmento se cierran explícitamente |
| Divulgación de información | Archivo de bloqueo creado con permisos 0o600 |

Para reportar una vulnerabilidad: escribe a **lab@morphilab.com** (no abras un
issue público). Consulta [`SECURITY.md`](SECURITY.md) para el proceso de
divulgación coordinada.

## Arquitectura

```
iterecho/
  cli.py                # App Typer, @app.callback() estilo Git + subcomandos
  models.py             # Dataclass FileEntry
  search.py             # FileSearcher — recorre base_dir, filtra por extensión/tamaño/seguridad
  processing.py         # FileProcessor — copy/concat/chunk + bloqueo fcntl
  security.py           # SecurityEngine — validación de rutas y enlaces simbólicos
  tui.py                # Modo interactivo basado en Rich
  config/               # Paquete de configuración
    models.py           # SearchConfig, OutputConfig, SecuritySettings, Mode + parse_size/fmt_size
    sanitize.py         # Listas CRITICAL/WARNING + sanitize_filename + is_safe_extension
    app.py              # AppConfig (delegación compatible con las dataclasses)
  utils/
    file_utils.py       # safe_file_copy / safe_read_file (O_NOFOLLOW, tmp atómico)
    logging.py          # setup_logging, variable ITERECHO_DEBUG
```

Los nuevos consumidores deben usar directamente las dataclasses (`SearchConfig`,
`OutputConfig`, `SecuritySettings`). `AppConfig` es un wrapper compatible.

## Desarrollo

```bash
uv sync --extra dev
source .venv/bin/activate

# Opcional: hooks de pre-commit (ruff, ruff-format, black, isort + higiene)
uv run --with pre-commit pre-commit install
```

Alternativa sin uv:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Ejecuta la puerta de calidad en local:

```bash
pre-commit run --all-files          # en una rama de trabajo; en main usa SKIP=no-commit-to-branch
uv run --no-sync ruff check iterecho/ tests/        # o simplemente ruff
uv run --no-sync black --check iterecho/ tests/     # o simplemente black
uv run --no-sync mypy iterecho/                      # mypy strict
uv run --no-sync pytest --cov=iterecho --cov-report=term-missing   # suite completa
uv build                     # valida sdist + wheel
```

## Pruebas

```bash
pytest                              # suite completa
pytest --collect-only -q | tail -1   # conteo exacto (nunca lo hardcodees)
pytest --cov=iterecho               # con cobertura
pytest tests/test_security.py       # un solo archivo
pytest -k "symlink"                 # coincidencia por patrón
```

La suite está organizada por área:

- `test_security.py` / `test_security_edge.py` / `test_security_paths.py` — invariantes de seguridad, enlaces simbólicos, carreras y rutas límite
- `test_file_utils.py` — `safe_file_copy`, `safe_read_file`
- `test_config.py` — `AppConfig`, `parse_size`, `is_safe_extension`
- `test_search.py` / `test_search_paths.py` — `FileSearcher` y rutas límite
- `test_processing.py` / `test_processing_unit.py` / `test_processing_errors.py` / `test_processing_lock.py` — `FileProcessor`, fallos y bloqueos
- `test_logging.py` — configuración del log y `ITERECHO_DEBUG`
- `test_main_module.py` — `python -m iterecho`
- `test_integration.py` — flujos de extremo a extremo de los tres modos
- `test_cli.py` — Typer CliRunner
- `test_tui.py` — TUI de Rich con mock de stdin

## Hoja de ruta

- [x] Bloqueo basado en `fcntl` en POSIX (respaldo `O_EXCL` + PID en Windows)
- [x] `--version` funciona sin subcomando
- [x] Tests de regresión por extensión (parametrizados)
- [x] Tests de regresión de enlaces simbólicos en el directorio padre
- [x] Bandit + pip-audit en CI
- [x] Hooks de pre-commit
- [ ] Modo vigilancia (procesamiento continuo ante cambios)
- [ ] Transformadores conectables (gzip, cifrado)
- [ ] Matriz opcional de `nox` para pruebas locales entre versiones

## Versiones de Python compatibles

3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14 — probadas en cada push a `main` y en
cada pull request mediante GitHub Actions.

## Contribuir

IterEcho lo mantiene un único propietario; por ahora no se aceptan pull
requests externos. Los informes de errores son bienvenidos mediante GitHub
Issues. Los informes de seguridad deben seguir [`SECURITY.md`](SECURITY.md) y no
deben abrirse como issues públicos.

## Licencia

MIT © morphilab. Consulta [`LICENSE`](LICENSE).
