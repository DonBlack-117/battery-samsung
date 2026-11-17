# Battery-Sam

Battery health dashboard for Samsung Android phones. It reads the phone over USB with ADB and shows live metrics, stored history, degradation and a refurbished-device check.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Live reading:** health %, real capacity, charge level, voltage, temperature and Android's own diagnosis.
- **History:** stores at most one reading every 10 minutes per model in SQLite, and charts the current session, the last 30 days or the last year.
- **Charge sessions:** one record per charge that starts at 20 % or less (the monthly 15 → 100 % charge), with the charge that went in, the capacity and health it implies, the peak temperature and the duration.
- **Degradation:** a least-squares trend over one reference charge per month (from 20 % or less to 100 %), or over daily averages of the readings until there are two reference charges a week apart, plus the estimated time until the battery reaches 80 %.
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
git clone https://github.com/DonBlack-117/battery-samsung.git
cd battery-samsung
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
```

## Usage

### Web dashboard

```bash
python app.py                 # same as: python -m battery_sam
```

Opens `http://127.0.0.1:5000`. The page refreshes every 30 seconds while the tab is visible.

### CLI

```bash
python bateria.py                       # single reading (auto-detects the model)
python bateria.py --watch 5             # refresh every 5 seconds
python bateria.py --json                # JSON output
python bateria.py --modelo "S23 Ultra"  # force a model
python bateria.py --lista-modelos       # supported models
python bateria.py --renovado            # refurbished-device report
python bateria.py --guardar             # also store the reading and track the charge session
python bateria.py --sesion              # record the charge in progress (reads every 60 s, stops when it ends)
python bateria.py --sesiones            # charge sessions on record (add --json for JSON)
```

### Charge sessions

The charge sessions follow a monthly routine: charge from about 15 % to 100 % once a month with the phone plugged into the laptop by USB, and either open the dashboard or run `python bateria.py --sesion`. The 10-minute reading history keeps working as before for the 30-day and 1-year charts.

- A session opens only on a reading with Android status «Cargando» (charging) at 20 % or less, while readings are being saved (model confirmed, or `--guardar` / `--sesion` in the CLI). Charges that start above 20 % are not recorded.
- It closes as complete when the phone reports full or 100 %.
- It closes as incomplete when «Proteger batería» stops it at 79 % or more (turn it off to reach 100 %), when the phone stops charging and the level drops 3 points below its peak (the session ends at that peak), or after 24 hours without readings.
- You can also charge from the wall: connect the phone at the start (charging over USB), unplug it, and connect it again at 100 %. Only the first and last readings matter.
- Session health = (charge counter at the end − at the start) / (end level − start level) × 100 / design capacity. It is calculated only when the session covered 50 points or more.
- Only one session per calendar month is compared: the complete one from 20 % or less to 100 % with the widest range (ties go to the latest). The dashboard and `--sesiones` mark it as «cuenta». The monthly degradation is a least-squares trend over those reference charges, and needs two of them at least 7 days apart.
- With a session open, the dashboard keeps reading even when its tab is hidden.

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
| `BATTERY_SAM_ALLOWED_HOSTS` | (empty) | Extra host names or IPs, comma separated, that may open the dashboard besides `localhost`, `127.0.0.1` and `BATTERY_SAM_HOST` |

Invalid values (port outside 1-65535, timeout of 0, refresh under 1000 ms) stop the program with a message.

## API

All endpoints take an optional `model` query parameter (default `S24 Ultra`). Errors come back as `{"error": {"code", "message"}}` with codes such as `no_device`, `unauthorized`, `adb_not_found`, `adb_timeout`, `bad_reading`, `unknown_model`, `db_unavailable` and `cross_site`.

The server only answers requests whose `Host` is local (or listed in `BATTERY_SAM_ALLOWED_HOSTS`), which blocks DNS rebinding. Requests to `/api/*` sent by another site (`Sec-Fetch-Site: cross-site` or `same-site`) get a 403, so a web page cannot trigger readings or writes. Every response carries a strict CSP, `X-Frame-Options: DENY` and `nosniff`. There is no `/docs` page. `/api/renovation` returns only the last 4 characters of the serial number (`serial_masked`).

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api/models` | Supported models and design capacities |
| GET | `/api/device` | Connected phone: model, brand, raw model, `is_samsung` |
| GET | `/api/current` | Current reading (stored if the interval has passed) |
| GET | `/api/renovation` | Refurbished-device report |
| GET | `/api/history?days=30` | Stored readings |
| GET | `/api/stats` | History summary and degradation trend (`trend_source`: `sessions` or `readings`) |
| GET | `/api/sessions?limit=24` | Charge sessions, newest first, and their summary |
| GET | `/api/export.csv` | CSV download |

## How battery health is calculated

1. **sysfs:** `charge_full` against `charge_full_design` from `/sys/class/power_supply/battery/`. If the units do not match, the model's design capacity is used instead. Android 14+ usually blocks this path.
2. **Estimate:** `charge_counter / level × 100`, only when the level is at least 20 %, because below that the error is too large.

Health = current capacity / design capacity × 100. Each reading needs a single `adb shell` call.

- Values from 50 to 101 % are normal readings. From 20 to 50 % the dashboard shows "Deficiente (verificar)": it may be a very worn battery or a bad measurement, so it is not stored. Below 20 % the reading is discarded.
- If `dumpsys battery` says `UPDATES STOPPED`, someone fixed the values with `dumpsys battery set`. The reading is marked as altered, it is not stored, and the refurbished report counts it as a risk. Restart the phone or run `adb shell dumpsys battery reset`.
- The refurbished report says "Sin datos suficientes" instead of "Bajo" when it could not read the health and neither the warranty bit nor the Knox fuse.

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
│   ├── sessions.py        # charge sessions: detection, storage and trend
│   ├── service.py         # glue used by the web app and the CLI
│   ├── cli.py, __main__.py
│   └── web/               # FastAPI app and response schemas
├── templates/index.html
├── static/
│   ├── js/                # ES modules: api, ui, reading, chart, summary, sessions, renovation, main
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
