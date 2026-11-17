# Referencias

Origen de cada regla o umbral del proyecto. «Heurística propia» marca lo que no viene de una fuente externa.

| Regla | Dónde | Fuente |
|---|---|---|
| `UPDATES STOPPED` en `dumpsys battery` indica valores fijados con `dumpsys battery set` o `unplug` | `battery_sam/device.py` (`is_overridden`) | Código de `BatteryService` de AOSP, `frameworks/base/services/core/java/com/android/server/BatteryService.java` (imprime `(UPDATES STOPPED -- use 'reset' to restart)` cuando `mUpdatesStopped`) |
| Salud normal entre 50 y 101 % | `battery_sam/health.py` (`PLAUSIBLE_MIN`, `PLAUSIBLE_MAX`) | Heurística propia |
| Entre 20 y 50 %: se muestra como «Deficiente (verificar)» y no se guarda | `battery_sam/health.py` (`VERY_LOW_MIN`) | Heurística propia (revisión Claude-Red 2026-11-15: antes una batería al 45 % desaparecía del informe) |
| Estimación solo con carga de 20 % o más | `battery_sam/health.py` (`MIN_LEVEL_FOR_ESTIMATE`) | Heurística propia |
| «Sin datos suficientes» si falta la salud y también el warranty bit y el fusible Knox | `battery_sam/renovation.py` | Heurística propia |
| Ciclos 50 / 150 / 300 | `battery_sam/renovation.py` (`CYCLE_*`) | Heurística propia |
| Bloqueo de `Sec-Fetch-Site: cross-site` y `same-site` en `/api/*` | `battery_sam/web/app.py` | W3C Fetch Metadata Request Headers; guía «Fetch Metadata» de web.dev (Resource Isolation Policy) |
| Validar `Host` contra DNS rebinding | `battery_sam/web/app.py` | Documentación de Starlette, `TrustedHostMiddleware` |
| Marcador de secciones con nonce por llamada | `battery_sam/adb.py` | Heurística propia (revisión Claude-Red 2026-11-15) |
| Salud por sesión: (charge_counter final − inicial) / (nivel final − inicial) × 100 / capacidad de diseño | `battery_sam/sessions.py` (`ChargeSession.capacity_mah`) | Heurística propia, sobre el `charge counter` (µAh) y el `level` que reporta `dumpsys battery` (documentación de `BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER` en developer.android.com) |
| Estados de carga 2 = cargando, 4 = sin cargar, 5 = llena | `battery_sam/sessions.py` (`STATUS_*`) | Documentación de `BatteryManager` (`BATTERY_STATUS_CHARGING`, `BATTERY_STATUS_NOT_CHARGING`, `BATTERY_STATUS_FULL`) en developer.android.com |
| La sesión solo se abre si la carga empieza en 20 % o menos | `battery_sam/sessions.py` (`MAX_START_LEVEL`) | Heurística propia (la carga mensual es de 15 a 100 %; 20 da margen) |
| Solo cuenta una carga por mes, completa de 20 % o menos a 100 %, la de rango más amplio | `battery_sam/sessions.py` (`reference_sessions`) | Heurística propia |
| Salud de sesión solo con 50 puntos de carga o más | `battery_sam/sessions.py` (`MIN_SPAN_FOR_HEALTH`) | Heurística propia |
| Cerrar la sesión si sin cargar el nivel baja 3 puntos del máximo | `battery_sam/sessions.py` (`DROP_TO_CLOSE`) | Heurística propia |
| Sesión abierta sin lecturas por 24 h se cierra como incompleta | `battery_sam/sessions.py` (`MAX_GAP`) | Heurística propia |
| Tendencia entre cargas de referencia con 2 o más separadas por 7 días o más | `battery_sam/sessions.py` (`summary`, usa `slope_per_day`) | Heurística propia (mismos umbrales que la tendencia por lecturas) |
