# Protokoll Home Assistant ↔ Display

So reden die Integration `matrixportal` (`custom_components/matrixportal/link.py`) und die
Firmware (`src/link.cpp`, `src/net.cpp`) miteinander. Aufbau wie bei SmartButtons.

**Aktuelle Version: 1.**

## Verbindung

- Das Display ist WebSocket-Server auf Port **81**, HA verbindet sich: `ws://<display>:81/`.
- Textframes mit genau einem JSON-Objekt, `type` bestimmt die Nachricht.
- Eine Verbindung zählt, eine neue ersetzt die alte.
- Heartbeat: Display pingt alle 15 s (trennt nach 2 verpassten Pongs), HA alle 10 s.
- Neustart des Displays: Es schließt die Verbindung vorher. HA versucht 120 s lang jede Sekunde,
  eine mDNS-Ankündigung löst sofort einen Versuch aus.
- Kein TLS. Die Kopplung schützt vor fremder Steuerung, nicht vor Mitlesen im LAN.
- Größte Nachricht ans Display: 24 KiB (`WEBSOCKETS_MAX_DATA_SIZE`), HA hält Kalender-Nachrichten unter 18 000 Byte.

## Ablauf

```
HA                                    Display
 |------------ verbinden ------------->|
 |<----------- hello ------------------|  nonce, id, Konfiguration, rev
 |  ungekoppelt:  pair --------------->|  → paired, neues hello
 |  gekoppelt:    auth (HMAC) -------->|  falsch → auth_failed, Display trennt
 |  Name anders:  name --------------->|  → renamed, Neustart
 |  rev anders:   config ------------->|  → config_saved, neues hello
 |  password ------------------------->|
 |  welcome -------------------------->|
 |<----------- status -----------------|  an, Helligkeit, Design ...
 |  event (Zustände) ----------------->|
 |        ... laufender Betrieb ...    |
 |<----------- get_calendar -----------|  alle 10 min, bei Tageswechsel, nach "refresh"
 |  calendar (je Kalender) ----------->|
 |  calendar_end --------------------->|
 |  set / command -------------------->|
 |<----------- status -----------------|  bei Änderung und alle 60 s
```

## Kopplung

- HA erzeugt pro Display 32 zufällige Bytes (64 Hex-Zeichen) und schickt sie mit `pair`.
- Jedes `hello` hat eine neue `nonce`. HA antwortet mit `auth`, `hmac = HMAC-SHA256(Schlüssel, nonce)` als Hex.
- Ungekoppelt nimmt das Display nur `pair` an, mit gesetztem Passwort nur mit diesem (`password`).
- Beim Koppeln löscht das Display den Long-Lived Token (HA liefert ab dann alle Daten).
- Lösen: `unpair` aus HA (Gerät in HA entfernen), Web-UI → System → „Kopplung lösen“, oder UP+DOWN
  beim Einschalten. Löscht Schlüssel und Passwort, das Display arbeitet wieder lokal.

## Nachrichten Display → HA

| `type` | Felder |
|---|---|
| `hello` | `proto`, `paired`, `mode` (`ha`/`local`), `nonce`, `id` (MAC, 12 Hex), `name`, `version`, `rev`, `protected`, `config`, `watch` |
| `status` | `on`, `brightness`, `demo`, `design`, `header`, `pac_every`, `strip_on`, `strip_brightness`, `strip_rgb` ([r, g, b]), `strip_count`, `strip_follow`, `view`, `effect`, `saver`, `saver_view`, `saver_from`, `saver_to` (`HH:MM`), `rssi`, `heap`, `uptime`, `ip`, `calendar` (1 ok, -1 Fehler, 2 keiner, 0 noch nicht), `events` |
| `get_calendar` | `id`, `calendars: [{entity, start, end}]` (ISO mit Offset; Arbeitskalender 7 Tage, sonst 1 Tag) |
| `paired`, `config_saved`, `renamed`, `unpaired` | – |
| `config_error`, `pair_error` | `message` |
| `auth_failed` | – (Display trennt danach) |

## Nachrichten HA → Display

| `type` | Felder | Wirkung |
|---|---|---|
| `auth` | `hmac` | Beweis |
| `pair` | `key`, `password` | Schlüssel übernehmen |
| `unpair` | – | Kopplung lösen |
| `config` | `rev`, `config` | Konfiguration speichern, kein Neustart, neues `hello` |
| `password` | `password` | Web-UI und OTA (Basic-Auth `admin:<Passwort>`), max. 32 Zeichen |
| `name` | `name` | Hostname (`a-z 0-9 -`, max. 31), Neustart |
| `welcome` | `ha_version`, `proto` | Ab jetzt laufen Zustände, Befehle, Kalender |
| `event` | `event.a` | Zustände wie `subscribe_entities`: `{"<entity>": {"s": state, "a": {...}}}` |
| `set` | `on`, `brightness` (1–255), `demo`, `design`, `header`, `pac_every` (0–1440), `strip_on`, `strip_brightness` (1–255), `strip_rgb` ([r, g, b]), `strip_count` (0–300), `strip_follow`, `view`, `effect`, `saver`, `saver_view`, `saver_from`, `saver_to` (`HH:MM`), alle optional | Laufzeit-Einstellungen, gespeichert (außer `demo`). `strip_*`, `view`, `effect`, `saver*` sind später dazugekommen, ältere Firmware ignoriert sie (HA zeigt die Entities dann als nicht verfügbar). `strip_brightness`/`strip_rgb` schalten den Strip ein, `strip_on` hat Vorrang |
| `command` | `command`: `restart`, `pacman`, `week`, `week_off`, `identify`, `refresh`, `doorbell`, `doorbell_off` | Aktion |
| `calendar` | `id`, `entity`, `ok`, `events: [{summary, location, start, end}]` | Termine eines Kalenders |
| `calendar_end` | `id`, `ok` | Anfrage fertig, Display übernimmt die Liste |

Werte: `view` = `dashboard`, `effekt`, `effekt_tage`, `effekt_laufband`, `effekt_liste`
(`saver_view` ohne `dashboard`); `effect` = `plasma`, `feuer`, `regen`, `sterne`, `polarlicht`, `lava`, `leben`, `ozean`, `glut`, `gluehwuermchen`, `schnee`, `feuerwerk`, `tunnel`, `regenbogen`, `kaleidoskop`, `aquarium`, `lavalampe`, `baelle`, `sanduhr`, `gewitter`, `labyrinth`, `wetter`, `solar`, `wechselnd`; `saver` = `aus`, `zeitfenster`, `keine_termine`, `beides`.

Weitergereichte Attribute: `unit_of_measurement`, `current_temperature`, `hvac_action`,
`temperature`. Beim Wetter zusätzlich `forecast_high`, `forecast_low` (heute, aus
`weather.get_forecasts`, alle 30 min). Unbekannte Entity: `"s": "unavailable"`.

HA liest nur Kalender, die in der Konfiguration des Displays stehen; andere bekommen `ok: false`.

### Konfiguration (`config`)

```json
{"solar": "sensor.pv", "office": "sensor.desk", "room": "climate.buero", "weather": "weather.home",
 "calendars": ["calendar.familie"], "work_calendar": "calendar.arbeit",
 "info": [{"entity": "sensor.bad_feuchte", "label": "Bad"}],
 "blockers": "Blocker,Block,Fokus,Focus", "tz": "CET-1CEST,M3.5.0,M10.5.0/3",
 "solar_max": 800, "office_max": 400}
```

Grenzen (Firmware `state.h`): Entity ≤ 63 Zeichen, Kalender zusammen ≤ 159, `info` ≤ 4 Einträge,
Kurzname ≤ 7 Byte, `blockers` und `tz` ≤ 63. `rev` = erste 12 Hex-Zeichen von SHA-1 über das
kompakte JSON mit sortierten Schlüsseln.

## Außerhalb von Port 81

- mDNS `_matrixportal._tcp` Port 81, TXT `id`, `name`, `version`, `proto`, `paired`, `mode`.
- Firmware-Update: `POST http://<display>/update`, Body = Image (`application/octet-stream`),
  Basic-Auth mit dem Passwort. Rollback, wenn das neue Image nicht 30 s mit WLAN läuft.
- `GET /update/status`: Version, Partition, Zustand (`pending_verify`/`valid`), verworfener Slot.

## Versionen

| Version | Firmware | Integration | Änderung |
|---|---|---|---|
| 1 | ab 1.0.0 | ab 1.0.0 | Erste Fassung |
