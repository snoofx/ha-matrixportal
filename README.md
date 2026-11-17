# MatrixPortal für Home Assistant

Integration für das MatrixPortal-S3-Tagesdisplay (192×64 LED). Home Assistant findet das Display
per mDNS, koppelt sich, liefert Zustände und Termine und bietet Entities zur Steuerung.

- Admin-Panel „MatrixPortal“ in der Seitenleiste (nur Admins): Konfiguration und Steuerung.
- Entities: Anzeige (Licht: an/aus, Helligkeit), Design, Kopfzeile, Demo-Modus, Pac-Man-Intervall,
  Neustart, Identifizieren, Pac-Man, Wochenübersicht, Kalender neu laden, Diagnose-Sensoren, Firmware-Update.
- Kein Token auf dem Display, Web-UI und OTA mit Passwort aus HA.
- Protokoll: [PROTOCOL.md](PROTOCOL.md).

Installation: `custom_components/matrixportal/` nach `<HA-config>/custom_components/` kopieren,
Home Assistant neu starten. Firmware zur Integration legen: `tools/bundle_ha.sh` im Firmware-Projekt.

Voraussetzung: Display-Firmware ab 1.0.0, Home Assistant ab 2025.1.
