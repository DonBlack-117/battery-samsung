# Battery-Sam

Battery health dashboard for Samsung Android phones. It reads the phone over USB with ADB and shows live metrics, stored history, degradation and a refurbished-device check.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Live reading:** health %, real capacity, charge level, voltage, temperature and Android's own diagnosis.
- **History:** stores at most one reading every 10 minutes per model in SQLite, and charts the current session, the last 30 days or the last year.
- **Degradation:** a least-squares trend over daily averages, plus the estimated time until the battery reaches 80 %.
- **Sanity checks:** readings outside 50–101 % are discarded instead of stored, and the dashboard says why there is no value.
- **Model detection:** recognizes 30+ Galaxy models (S, Note and A series). Other brands are shown by name.
- **Refurbished check:** cycle count, Knox warranty bit, Knox hardware fuse and battery health. Data the phone does not expose is listed as unverified rather than counted as a risk.
- **Battery protection:** reads One UI's «Protect battery» setting when the phone allows it.
- **CSV export** per model, and a **CLI** with watch mode and JSON output.
- Works offline: Chart.js and the Geist fonts are bundled in `static/vendor/`.

## Requirements

- Python 3.10+
- A Samsung phone with **USB debugging** enabled, and a USB cable
- ADB: bundled in `adb/` for Windows; on Linux and macOS install `android-tools` / `platform-tools`

## Installation

```bash
git clone https://github.com/DonBlack-117/battery-samung.git
cd battery-samung
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
```

## Usage

### Web dashboard

```bash
python app.py                 # same as: python -m battery_sam
```

Opens `http://127.0.0.1:5000`. The page refreshes every 30 seconds while the tab is visible. Interactive API docs are at `/docs`.

### CLI

```bash
python bateria.py                       # single reading (auto-detects the model)
python bateria.py --watch 5             # refresh every 5 seconds
python bateria.py --json                # JSON output
python bateria.py --modelo "S23 Ultra"  # force a model
python bateria.py --lista-modelos       # supported models
python bateria.py --renovado            # refurbished-device report
python bateria.py --guardar             # also store the reading in the history
```

### Configuration

Environment variables, all optional:

| Variable | Default | Meaning |
|---|---|---|
| `BATTERY_SAM_DB` | `data/battery_data.db` | SQLite file |
| `BATTERY_SAM_PORT` | `5000` | Web port |
| `BATTERY_SAM_HOST` | `127.0.0.1` | Web host |
| `BATTERY_SAM_SAVE_INTERVAL` | `600` | Minimum seconds between stored readings |
| `BATTERY_SAM_REFRESH_MS` | `30000` | Dashboard refresh interval |
| `BATTERY_SAM_ADB_TIMEOUT` | `10` | ADB timeout in seconds |

## API

All endpoints take an optional `model` query parameter (default `S24 Ultra`). Errors come back as `{"error": {"code", "message"}}` with codes such as `no_device`, `unauthorized`, `adb_not_found`, `adb_timeout` and `unknown_model`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/models` | Supported models and design capacities |
| GET | `/api/device` | Connected phone: model, brand, raw model, `is_samsung` |
| GET | `/api/current` | Current reading (stored if the interval has passed) |
| GET | `/api/renovation` | Refurbished-device report |
| GET | `/api/history?days=30` | Stored readings |
| GET | `/api/stats` | History summary and degradation trend |
| GET | `/api/export.csv` | CSV download |

## How battery health is calculated

1. **sysfs:** `charge_full` against `charge_full_design` from `/sys/class/power_supply/battery/`. If the units do not match, the model's design capacity is used instead. Android 14+ usually blocks this path.
2. **Estimate:** `charge_counter / level × 100`, only when the level is at least 20 %, because below that the error is too large.

Health = current capacity / design capacity × 100. Each reading needs a single `adb shell` call.

## Project structure

```
battery-sam/
├── app.py, bateria.py     # shortcuts for the server and the CLI
├── battery_sam/
│   ├── adb.py             # ADB client (one shell per reading, typed errors)
│   ├── catalog.py         # models, capacities, labels
│   ├── device.py          # raw reads: battery, model, refurbished indicators
│   ├── health.py          # health calculation and plausibility checks
│   ├── renovation.py      # refurbished-device risk analysis
│   ├── storage.py         # SQLite history and degradation trend
│   ├── service.py         # glue used by the web app and the CLI
│   ├── cli.py, __main__.py
│   └── web/               # FastAPI app and response schemas
├── templates/index.html
├── static/
│   ├── js/                # ES modules: api, ui, reading, chart, summary, renovation, main
│   ├── style.css
│   └── vendor/            # Chart.js and fonts
└── tests/                 # pytest + Playwright, with a fake phone
```

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium
.venv/bin/python -m pytest              # unit, API and browser tests
.venv/bin/python -m pytest tests/e2e    # browser tests only
```

The tests never touch a real phone: `tests/fakes.py` answers like ADB with a captured `dumpsys battery`.

## License

MIT. See [LICENSE](LICENSE).

The ADB binaries bundled in `adb/` come from the Android Open Source Project under the Apache 2.0 License (see `adb/notice.txt`).
