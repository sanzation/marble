# Marble v0.0.2 — Nachtrag: Schulen-Testfall (ersetzt den Dublin-Beispielkontext in Abschnitt 5)

**Stand:** 2026-11-01. Gilt zusätzlich zu `MARBLE_CODEX_HANDOFF.md`; bei Widerspruch gilt dieser Nachtrag.

## 1. Was sich ändert
- Der fachliche Testfall ist nicht mehr "Behörden-Aliase" (`DCC`), sondern **Schulverzeichnisse deutscher Bundesländer**.
- Das `DCC`-Prinzip bleibt, nur mit neuem Beispiel: **`KGS`** ist mehrdeutig (Katholische Grundschule / Kooperative Gesamtschule) und in `nondomain_kgs.csv` schlicht Kilogramm.
- Neue Fixtures liegen unter `examples/schulen_de/` (siehe dortige README). Die v0.0.1-Fixtures `examples/three_csv/` bleiben **unverändert** als Baseline.
- Ground Truth (`truth.json`) ist vorab gelabelt. Tests werden **gegen diese Datei** geschrieben, bevor Code entsteht.

## 2. Was die Engine zusätzlich können muss (klein halten)
1. **CSV-Ingestion robuster:** Encoding (UTF-8 und cp1252), Trennzeichen `;`/`,`, mit Erkennung und Protokollierung der Wahl als Evidenz. Rohwerte unverändert.
2. **Alias-Pack laden** (`alias_packs/schulen-de.json`), nur wenn aktiv, nur im angegebenen `field_scope`. Ohne aktives Pack: keine Alias-Vorschläge.
3. **Mehrdeutige Einträge** (`ambiguous: true`): nur `accepted`, wenn eine explizite `context_rule` greift; sonst `review` mit Kandidatenliste.
4. **Keine zirkuläre Evidenz:** Eine Normalisierung darf nicht allein auf einer ungeprüften Match-Hypothese beruhen. Sie bleibt `review`.
5. **Widersprüchliche IDs:** Name+Adresse gleich, aber ID widerspricht -> Match-Hypothese `review`, niemals `accepted`.
6. **Laufende Nummer ist keine ID:** Spalte `Nr.` (ddorf) wird nicht auf `school_id` gemappt.
7. **Zusammengesetzte Felder** (`Adresse` vs. `Strasse`+`Hausnummer`): Schema-Hypothese `review`, keine stille 1:1-Zuordnung.
8. **Koordinaten:** nur Spaltenzuordnung als `review` (CRS nicht deklariert oder unterschiedlich). **Keine CRS-Transformation in v0.0.2.**

Stretch (nur wenn Kernumfang grün ist): `parse_date_de`, `parse_decimal_de` (reine Formatprüfung, siehe `N11`/`N12`).

## 3. Akzeptanzkriterien (zusätzlich zu Abschnitt 5E)
- Jede Zeile in `truth.json -> expected_normalization` (außer `tier: stretch`) wird mit der angegebenen `disposition` erzeugt.
- Alle Paare in `must_not_merge` ergeben **keine** `accepted`-Match-Hypothese.
- `E04` (widersprüchliche Schulnr) ist `review`.
- `nondomain_kgs.csv` erzeugt mit aktivem Pack **keinen** `alias_lookup`-Vorschlag.
- Globale Invarianten: 0 Entity-Merges, 0 geänderte Rohwerte, 0 verlorene Spalten, deterministische IDs über zwei Läufe.
- Alte Reports und Schemas bleiben lesbar (nur additive Änderungen).
- Tests mit `cp1252`-Datei: Lesen ohne Mojibake, Rohwert-Roundtrip erhalten.

## 4. Provenienz (additiv)
Pro Quelle optionale Felder `license`, `license_url`, `publisher`, `retrieved_at`, `declared_crs`. In v0.0.2 nur durchreichen und im Report ausgeben, keine Logik darauf aufbauen.

## 5. Nicht in v0.0.2
Keine CRS-Transformation, keine Adress-Geokodierung, keine Excel-/WFS-/GeoJSON-Adapter, kein LLM, keine Merges, kein Cross-Country-Alias-Wissen außerhalb des Packs.

## 6. Ergänzung zum Startprompt (Abschnitt 8)
> Nutze für v0.0.2 zusätzlich `examples/schulen_de/` und `MARBLE_V002_SCHULEN_ADDENDUM.md`. Schreibe zuerst Tests gegen `truth.json`, dann die Implementierung. Berichte die Abweichungen zwischen erwarteter und erzeugter Disposition je `N`-ID, nicht nur eine Pass-Quote.
