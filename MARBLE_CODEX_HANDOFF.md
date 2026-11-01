# Marble — Konzept und Codex-Übergabe

**Stand:** 2026-11-01  
**Vorhandener Prototyp:** v0.0.1, `marble-core-v0.0.1.zip`  
**Nächster Zielstand:** v0.0.2 — evidence-first semantic normalization discovery, weiterhin ohne automatische Entity-Merges.

## 1. Produktidee und Positionierung

**Marble** ist eine **local-first, open-source Data-Harmonization-Engine**: *Throw messy data in; get explainable, clean, queryable entities out.*

Langfristig soll Marble inkompatible Dateninseln (CSV, JSON, HTML-Tabellen, GeoJSON, HTTP-APIs) möglichst ohne manuelles ETL-Setup einlesen, deren fachliche Struktur erkennen, gleichbedeutende Felder und Werte normalisieren, identische Entitäten über Quellen hinweg finden und die konsolidierten Fakten kompakt, mit Herkunftsnachweisen und Konflikten, für SQL/ML/LLM-Nutzung bereitstellen.

**Primärer Differenzierungsversuch:** minimaler Setup-Aufwand, reproduzierbare Data Discovery und nachvollziehbare Ergebnisse. Nicht „noch ein allgemeines RAG-/LLM-Framework“. Der wertvolle Kern ist die Strecke **zwischen Datei einlesen und fachlich korrekt konsolidierter Entität**.

**Langfristige Pipeline:**

```text
heterogene Quellen
  -> Input Adapter / Raw Record Staging
  -> Profiling und Datentyp-/Entity-Grain-Hypothesen
  -> Schema Discovery (Spaltenzuordnung)
  -> Value Normalization (Formate, Aliases, Einheiten)
  -> Record-/Entity-Matching
  -> Fact Fusion (Konflikte, zeitliche Gültigkeit, Provenienz)
  -> kanonisches Marble-Modell
  -> DuckDB / SQL, JSON, Parquet, später ggf. eigenes Marble-Format
  -> optional kontextoptimierte ML-/LLM-Projektionen
```

Ein künftiges eigenes Datenformat bleibt offen. **Jetzt keine eigene Storage-Engine und keinen Codec implementieren.** DuckDB ist der vorläufige Speicher, keine Festlegung des fachlichen Marble-Modells.

## 2. Architekturprinzipien

1. **Local first, zero cloud dependency:** Standardpipeline ohne API-Keys, Cloudservice und Docker nutzbar.
2. **Simple public API / CLI:** Wenige Argumente, möglichst automatische Vorschläge, aber sichere Defaults.
3. **Evidence first:** Jede Feld-, Typ-, Entitäts- oder Normalisierungshypothese hat Score, Evidenz, Tests und Disposition. Ein numerischer Heuristik-Score ist **keine** kalibrierte Wahrscheinlichkeit.
4. **Safety of data:** Keine stillschweigenden Änderungen, keine verlorenen Spalten, kein unbemerkter Merge; Konflikte und negative Gegenbeispiele explizit erhalten.
5. **Discovery != Execution:** Discover erstellt Hypothesen und Recipe-Drafts; nach bestätigter Prüfung führen versionierte Recipes deterministische Transformationen aus.
6. **Reproducibility:** Gleiche Inputs und Konfiguration ergeben die gleichen, geordneten Ergebnisse; Entscheidungen müssen debugbar sein.
7. **Modularity:** Input-Adapter, Discovery, Transformationslogik, Matching und Storage sind getrennt; bestehende Interfaces/JSON-Schemas respektieren.
8. **Quality over feature count:** Erst die drei CSV-Quellen korrekt verstehen, dann weitere Quellformate.

## 3. Vorgesehener Tech-Stack (nicht alles schon im Code vorhanden)

- **Python 3.12+**, Pydantic v2, pytest, Typer/CLI (bestehendes Prototype-CLI prüfen statt blind neu zu erstellen).
- **DuckDB** für optionalen lokalen Snapshot; im Prototype bereits `InspectionStore`-Abstraktion.
- **Polars** für zukünftige vektorisierte Normalisierung, **Apache Arrow** als künftige Batch-Schnittstelle; momentan im Prototype überwiegend Pydantic-Records, `to_arrow()` optional. Keine voreilige Komplettmigration.
- **RapidFuzz**, ggf. **Valentine / Splink / scikit-learn** erst nach messbarem Bedarf, als optionale Erweiterungen.
- Optional später: Geo-Adapter mit WKB/Spatial; HTTPX, HTML-Parser; ML-/LLM-Fallback nur für nicht hinreichend regelbasiert lösbare Fälle.
- **Keine Microservices, kein Frontend, kein Agent Framework** in der Kernversion.

## 4. Tatsächlicher Stand von v0.0.1 — anhand der Dateien geprüft

Repo-/Archivstruktur:

```text
src/marble/
  __init__.py       öffentliche Funktion inspect_csvs()
  cli.py            marble inspect / marble explain
  ingest.py         CSV-Ingestion
  profile.py        Spalten-/Werteprofilierung
  semantics.py      domänenspezifische Heuristiken/Aliaswissen
  discovery.py      Hypothesen, Checks, Entity-Grain-/Record-Match-Vorschläge
  pipeline.py       Inspektion, Export und Metriken
  models.py         Pydantic-Verträge
  storage.py        InspectionStore und optional DuckDBInspectionStore
examples/three_csv/
  dcc_register.csv, council_extract.csv, gis_sites.csv
  truth.json, sample_output/
docs/
  CONTRACTS.md, schemas/*.schema.json
tests/
  test_inspection.py, test_labelled_baseline.py,
  test_duckdb_optional.py
```

**Tatsächlich implementiert:**

- CSV-Batch-Import, Rohwerte unverändert erhalten, Profile pro Feld und Quelle.
- Heuristische Feldzuordnungen zu kleiner **bekannter** Test-Ontologie (`register_id`, `address`, `local_authority`, `status`, `recorded_date`, `latitude`, `longitude`). Das ist keine generische automatische Ontologie-Erkennung.
- Vermutungen zum Entity-Grain (`site`, `event`, `organization`) und zu paarweisen Record-Übereinstimmungen.
- Jede `Hypothesis` hat Evidenz, Checks, Score und Status (`accepted`, `review`, `rejected`); `accepted` bedeutet nur **regelgestützt**, nicht menschlich verifiziert.
- `RecipeDraft` ist **nicht ausführbar** und hat `resolution_policy=no_merges`.
- `CanonicalPreview` enthält nur sicher benannte Zielfelder mit **unveränderten Rohwerten**, andere Daten in `unmapped_fields`.
- JSON/CSV-Reports, optionale persistierte **Inspection-Snapshots** in DuckDB, kein persistenter kanonischer Entity Store.
- `inspect_csvs()` akzeptiert 2 bis 20 CSVs. Der DuckDB-Snapshot wird pro Lauf transaktional **ersetzt**, nicht inkrementell ergänzt.
- Aus dem enthaltenen Beispielreport: 3 Quellen, 12 Source Records, 43 Hypothesen, 12 akzeptierte Feldhypothesen, 4 Review-Feldhypothesen, 8 akzeptierte **Record-Match-Hypothesen**, 10 verworfene Match-Hypothesen und **0 tatsächliche Merges**.
- Lokal erneut ausgeführt: `python -m pytest -q` -> **12 passed, 1 skipped**. Übersprungen ist der optionale DuckDB-Integrationstest (Abhängigkeit in der aktuellen Umgebung nicht verfügbar); nicht als erfolgreich getestet behaupten.

**Nicht vorhanden:** ML-/LLM-Verarbeitung, echte Value-Normalization, automatisches Schema-Lernen auf beliebige Domains, ausführbare Recipe-Transformationen, persistente Entity-/Fact-Fusion, Auto-Merge, APIs/HTML/GeoJSON-Ingestion, eigener Kompressionscodec.

**Aktuelle Verträge nicht brechen:** `docs/CONTRACTS.md`, `docs/schemas/*.schema.json`, Pydantic-Modelle in `models.py`. Schemaänderungen ausschließlich additiv mit angepassten Schemas/Tests oder mit expliziter Versionierung/Migration.

## 5. NÄCHSTER CODEX-AUFTRAG — v0.0.2 (nur ein kleiner vertikaler Schritt)

**Ziel:** Erste selbständig *vorgeschlagene* **Wertnormalisierung** über mehrere CSV-Quellen. Beispielsweise können `Dublin City Council`, `DCC`, `Dublin City` in einem `local_authority`-Feld dieselbe Behörde meinen. Die Engine soll die Vermutung **erklären und testen**, aber vor Freigabe **keine Rohdaten ändern** und **keine Records mergen**.

### Aufgabe A — Baseline absichern

1. Bestehenden Code und `docs/CONTRACTS.md` lesen; Tests ausführen. Ergebnisse und eventuelle Umgebungslücken berichten.
2. Die bestehende `inspect_csvs()`-API und CLI-Befehle `marble inspect`, `marble explain` erhalten.
3. Die vorhandenen synthetischen Fixtures und Ground Truth unverändert als Baseline behalten. Zusätzliche Fixtures separat anlegen.
4. In Test- und Nutzertexten konsequent zwischen `heuristically_accepted`, `human_confirmed` und `rejected` unterscheiden. Wenn interne Statusbezeichnungen nicht sofort geändert werden, ausdrücklich die Semantik dokumentieren.

### Aufgabe B — Normalization-Proposal-Kontrakt

Additiv einen Pydantic-Typ (`ValueNormalizationProposal` oder äquivalent) mit mindestens folgenden Feldern definieren:

- `proposal_id`, `schema_version`, `source_id`, `source_field`, `canonical_field`
- `raw_value`, `proposed_value`, `operation` (zunächst z. B. `trim`, `casefold`, `alias_lookup`)
- `evidence[]`, `checks[]`, `score` (heuristisch), `disposition` (`accepted`/`review`/`rejected` oder klarere äquivalente Semantik)
- `recipe_candidate` oder eine Referenz, die zur späteren Recipe-Erstellung geeignet ist

Einfachheit vor übermäßigem Abstraktionsaufwand. Nachvollziehbare JSON-Serialisierung und Schema-Export erforderlich. Bestehende Report-Verträge nur additiv erweitern.

### Aufgabe C — Explizit getrennte Hypothesengenerierung und Prüfung

1. Schema-Mapping (`Council` -> `local_authority`) und Werte-Alias (`DCC` -> `Dublin City Council`) **unterschiedlich modellieren**.
2. Deterministische Kandidaten-Erzeugung aus Spaltenwertverteilungen, Normalform (Trim/Whitespace/Case), Cross-Source-Overlap und opt-in konfigurierbaren Alias-Tabellen.
3. Eine **konfigurierbare** Quelle für Domänen-Aliases einführen; keine nicht belegbaren universellen Abkürzungsregeln (`DCC` kann in anderem Kontext etwas anderes heißen).
4. Positive Evidenz und Gegenbelege/Mehrdeutigkeiten ausgeben. Bei Mehrdeutigkeit/fehlender Evidenz `review`, nicht stillschweigend `accepted`.
5. `DCC`, `Dublin City` und `Dublin City Council` als mögliches Match erkennen, nur wenn Testkontext/gespeicherte Regeln diese Schlussfolgerung rechtfertigen.
6. Für eine **nicht-domänenspezifische** neue Fixture prüfen, dass `DCC` nicht automatisch als Behörde interpretiert wird.

### Aufgabe D — Debugging und Outputs

1. Die neue Normalisierungs-Hypothese im `InspectionReport` oder einem per Run referenzierten Dokument speichern, ohne bestehende JSON-Schlüssel zu entfernen.
2. Ein maschinenlesbares `normalization_proposals.json` und ein kompakter Debug-Report (CSV oder CLI-Ausgabe) sind sinnvoll.
3. `marble explain` um eine Abfrage einer Normalisierungshypothese erweitern, mit Rohwert, Zielwert, allen Evidenzen, Checks und Ablehnungsgrund.
4. `RecipeDraft` enthält **nur vorgeschlagene** Transformationsoperationen, nicht deren automatische Ausführung. Rohwerte und `canonical_preview` bleiben zunächst unverändert.
5. Alle neuen Interfaces und JSON-Schemas unter `docs/CONTRACTS.md` und `docs/schemas/` dokumentieren.

### Aufgabe E — Tests / Akzeptanzkriterien

Schreibe **zuerst** kleine, handgelabelte Testfälle (positive und negative) und halte die erwarteten Resultate vor der Implementierung fest:

- Drei Spaltennamen aus drei CSVs werden zur selben Ziel-Eigenschaft vorgeschlagen.
- Identische Strings nach `trim`, Whitespace-Normalisierung und Casefolding liefern erklärbare Kandidaten.
- Behörden-Aliases werden nur auf Basis expliziter/eindeutig belegter Zuordnung vorgeschlagen.
- Mehrdeutige Kurzform `DCC` ohne Kontext -> `review`, **kein** Auto-Mapping.
- Falsche Lookalikes und widersprüchliche IDs -> **kein** Entity-Merge.
- Kein Input-Rohwert und keine unbekannte Spalte geht verloren.
- Zwei Läufe mit denselben Inputs ergeben deterministisch identische Ergebnisse und stabile IDs.
- JSON-Ausgaben validieren gegen Pydantic/JSON-Schema; bestehende Konsumenten können alte Felder weiter lesen.
- `pytest -q` für die vorhandenen und neuen Tests ohne Regression. Optionaler DuckDB-Test läuft, falls DuckDB installiert; sonst Skip ausdrücklich vermerken.

**Definition of Done v0.0.2:** Von den drei CSVs wird mindestens ein fachlich sinnvoller, explizit belegter Wertnormalisierungsvorschlag erzeugt; ein mehrdeutiger Gegentest wird korrekt zur Prüfung zurückgehalten; jeder Vorschlag kann über CLI/JSON erklärt werden; Rohwerte sind unverändert und es gibt weiterhin **0 echte Entity-Merges**.

## 6. Danach — bewusst als separate Inkremente, NICHT jetzt alles implementieren

**v0.0.3 — Schema-Discovery verbessern:** Ein-zu-eins-Zuordnungen von Quellspalten zu Zielfeldern prüfen, Mehrdeutigkeiten und unterschiedliche Entitätstypen erkennen, Score-Evaluation auf echten Holdout-Datasets. Erst wenn der Regeln-Ansatz unzureichend ist, ML-Fallback mit messbarer Baseline integrieren.

**v0.0.4 — Recipe Approval + Execution:** `RecipeDraft` -> geprüfte, versionierte Recipe-Definition -> deterministischer Transformationsplan. Rohdaten/normalisierte Projektion getrennt. Kein willkürliches Python aus untrusted Recipes ausführen.

**v0.0.5 — Entity-Identity PoC:** stabile Business Keys, sichere Blocking-Strategien, Matching-Proposals und *nur explizit freigegebene* Merges; Source-Links, Fehlerkorrektur und Provenienz. Fact Fusion anschließend separat.

**v0.1 — zusätzliche Adapter:** JSON/HTML-Tabellen/GeoJSON/API hinter demselben `SourceBatch`-Vertrag; HTTP als Transport, nicht als semantisches Format. Für URLs: Sicherheitsgrenzen, Timeout, Downloadlimit, keine unkontrollierten internen Netzwerkzugriffe.

**Langfristig:** persistentes `Entity`/`Fact`/`Assertion`-Modell, SQL/JSON/Parquet-Projektionen, inkrementelle Verarbeitung, ML-Assistenz, Benchmarks für Entity-/Kontextkompression gegen DuckDB/Parquet, eventuell ein spezielles Marble-Format.

## 7. Entwicklungsmodus für Codex

- In **kleinen PRs oder Commits** arbeiten: erst Fixtures/Expected Outcomes, dann Implementierung, dann Regressionstests, Dokumentation und Beispielreport.
- Vor größeren Refactorings Architekturannahmen explizit machen. Bestehende v0.0.1-Verträge nach Möglichkeit beibehalten.
- Kein generisches Framework hinzufügen, wenn 50–100 Zeilen einfacher Code das konkrete Testproblem ausreichend lösen.
- Kein LLM-Aufruf im Default-Flow; keine neuen schweren Dependencies ohne messbaren Nutzen.
- Keine perfekte Match-Qualität auf den Toy-Daten als Beleg für Generalisierbarkeit verkaufen. Neben den Positivfällen stets negative, domänenfremde und adversariale Beispiele testen.
- Für jeden Vorschlag **Warum? Welche Evidenz? Welcher Gegenbeweis? Welche Validierung?** dokumentieren.
- Keine stillschweigende Überschreibung fachlicher Werte und keine unautorisierte Zusammenführung.
- Zum Abschluss liefern: geänderte Dateien, Testresultate, Beispiel `marble explain`, vor/nach Metriken, bekannte Unsicherheiten und **einen** nächsten empfohlenen Schritt.

## 8. Konkreter Startprompt für Codex

> Du arbeitest am beigefügten Marble-Core-Repository (v0.0.1). Bitte lies zunächst `README.md`, `docs/CONTRACTS.md`, die Pydantic-Modelle, `src/marble/discovery.py`, `src/marble/semantics.py` und alle Tests. Führe die existierende Test-Suite aus. Implementiere ausschließlich den in Abschnitt 5 beschriebenen v0.0.2-Schritt: erklärbare, getestete **Value-Normalization-Proposals** über die vorhandenen drei CSV-Quellen, mit konfigurierbaren Alias-Regeln, klaren Checks/Evidenzen, negativer Mehrdeutigkeitsprüfung, JSON-Schema/CLI-Explain und erweiterten Ground-Truth-Tests. Halte Eingaben, öffentliche API, Rohdaten und alte Output-Verträge stabil. Keine echten Normalisierungsschreibvorgänge, keine Entity-Merges, kein LLM, kein neues Inputformat, kein Frontend. Arbeite testgetrieben und berichte explizit, was implementiert und geprüft wurde sowie was weiterhin nur geplant ist.
