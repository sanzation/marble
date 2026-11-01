# examples/schulen_de — Fixtures für Marble v0.0.2

**Alle Daten sind synthetisch.** Schulen, Nummern, Adressen, Mailadressen und Koordinaten sind erfunden.
Struktur und Eigenheiten (Trennzeichen, Encoding, Dezimalkomma, zusammengesetzte Adressen, CRS) sind an reale
Landesverzeichnisse angelehnt, aber nicht 1:1 kopiert. Die Ground Truth (`truth.json`) wurde **vor** der Implementierung gelabelt.

| Datei | Rolle | Eigenheiten |
|---|---|---|
| `nrw_landesverzeichnis.csv` | Landesverzeichnis (NRW-Stil) | UTF-8, `;`, Dezimalkomma, Strasse/Hausnummer getrennt, CRS nicht deklariert |
| `berlin_schulverzeichnis.csv` | Landesverzeichnis (Berlin-Stil) | UTF-8, `,`, Dezimalpunkt, Straße+Nr kombiniert, CRS im Spaltennamen (EPSG:25833), eigenes ID-System (BSN) |
| `duesseldorf_excel_export.csv` | kommunale Excel-Liste | **cp1252**, `;`, Adresse in einer Zelle, Abkürzungen, Leerzeichen, Duplikat innerhalb der Quelle, widersprüchliche Schulnr |
| `nondomain_kgs.csv` | Gegentest | `KGS` = Kilogramm; darf nie als Schulform interpretiert werden |
| `alias_packs/schulen-de.json` | opt-in Alias-Pack | feld-gescoped, mehrdeutige Einträge mit Kandidaten + Kontextregeln |
| `truth.json` | Ground Truth | Entities, Must-not-merge, erwartete Normalisierungs-Dispositionen |

## Was die Fixtures testen
- Dedupe passiert **innerhalb eines Landes über Anbieter hinweg** (Landesverzeichnis vs. Kommune), nicht zwischen Ländern. Zwischen Ländern ist die Aufgabe Schema-/Wert-Harmonisierung.
- Cross-State-Lookalikes (gleicher Name, sogar gleiche Straße+Nr) dürfen **nicht** gemerged werden.
- `KGS` ist mehrdeutig (Katholische Grundschule / Kooperative Gesamtschule): Kontextregel -> `accepted`, ohne Kontext -> `review`.
- Evidenz aus einer unbestätigten Match-Hypothese darf eine Normalisierung nicht allein auf `accepted` heben (zirkuläre Evidenz).

## Echte Daten später (separat, nicht ins Repo kopieren ohne Lizenzprüfung)
Lizenz und Attribution pro Quelle in der Provenienz festhalten (z. B. dl-de/by-2.0, dl-de/zero-2.0).
