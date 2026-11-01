# Schulen-DE: Ergebnis vom 01.11.2026

Der v0.0.2-Schritt aus `MARBLE_CODEX_HANDOFF.md` und dem Schulen-Nachtrag ist
implementiert. Tests gegen die unveränderte `truth.json` wurden zuerst geschrieben
und rot ausgeführt, danach folgte die Implementierung.

Vorher: 13 bestehende Tests grün. Die neue Akzeptanz-Suite meldete zunächst
6 fehlgeschlagene Tests und 22 Setup-Fehler: insbesondere fehlendes `alias_packs`,
fehlende Normalisierungsvorschläge und cp1252-Decoding. Originalprotokoll:
[`before-tests.txt`](before-tests.txt). Auch ohne Pack-Argument scheiterte der
bisherige vollständige Schulen-Lauf am cp1252-Encoding.

Nachher: **46 Tests bestanden**, einschließlich DuckDB, CLI und JSON Schema.
Pyright über `src`, `tests`, `scripts`: **0 Fehler, 0 Warnungen**.

## Erwartung gegen tatsächliche Disposition je N-ID

Vorher wurde für keine N-ID ein Normalisierungsvorschlag erzeugt; der vollständige
Original-Lauf war zusätzlich vom Encoding blockiert. `not_generated` wird nicht
als von der Engine erzeugtes `rejected` ausgegeben.

| ID | Operation | Erwartet | Erzeugt | Abweichung |
|---|---|---|---|---|
| N01 | trim | accepted | accepted | keine |
| N02 | casefold | accepted | accepted | keine |
| N03 | alias_lookup | accepted | accepted | keine |
| N04 | alias_lookup | accepted | accepted | keine |
| N05 | alias_lookup | accepted | accepted | keine |
| N06 | alias_lookup | accepted | accepted | keine |
| N07 | alias_lookup | accepted | accepted | keine |
| N08 | alias_lookup | review | review | keine |
| N09 | alias_lookup | review | review | keine |
| N10 | category_equivalence | review | review | keine |
| N11 | parse_date_de (Stretch) | accepted | accepted | keine |
| N12 | parse_decimal_de (Stretch) | accepted | accepted | keine |

Zielwerte und Kandidatenlisten stimmen ebenfalls überein. N11 deckt alle acht
Düsseldorf-Zeilen ab. N12 formatiert nur Zahlen; keine CRS-Transformation.
N02 vergleicht mit Casefold und wählt einen tatsächlich beobachteten
Repräsentanten; `casefold()` allein erzeugt keine Großschreibung.
Details und Proposal-IDs: [`evaluation.json`](evaluation.json),
[`normalization-dispositions.csv`](normalization-dispositions.csv).

`accepted` bedeutet **heuristisch akzeptiert**, nicht menschlich bestätigt.
Alle Vorschläge bleiben im nicht ausführbaren Recipe-Draft; die
Wertnormalisierung verändert weder Rohwerte noch Preview.

## Fixture-Ergebnis und Gegenbeispiele

- 4 Quellen, 26 Zeilen: NRW 8, Berlin 6, Düsseldorf 8, domänenfremd 4.
- 38 Vorschläge: 33 heuristisch akzeptiert, 5 zur Prüfung. Die zwölf gelabelten
  Fälle werden separat bewertet; für die übrigen besteht kein vollständiges Labelset.
- N07 wird nur durch `Schulart=Gesamtschule` aufgelöst. N08 behält beide
  KGS-Kandidaten; der Träger ersetzt keine explizite Regel. N09 bleibt trotz
  möglicher NRW-Match-Hypothese mehrdeutig. N10 bleibt approximative Äquivalenz.
- `unit=KGS` erzeugt keinen Alias-Vorschlag. Ohne aktives Pack gibt es keine
  Alias- oder Kategorieäquivalenz-Vorschläge.
- Alle sieben gelabelten positiven Record-Paare erscheinen als Kandidaten,
  einschließlich des Duplikats innerhalb Düsseldorfs: ein Paar heuristisch
  akzeptiert, sechs zur Prüfung. E04 bleibt wegen widersprüchlicher Schulnummern
  ausdrücklich `review`.
- Kein `must_not_merge`-Paar ist akzeptiert: zwei explizit abgelehnt, drei ohne
  Kandidaten. Ein fehlender Kandidat wird nicht als geprüfte Ablehnung bezeichnet.
  Kein akzeptiertes Paar liegt außerhalb der gelabelten Entities dieses Fixtures.
- **0 Merges, 0 ausgeführte Normalisierungen, 0 geänderte Rohwerte, 0 verlorene
  Spalten.** Zwei Läufe liefern identische Reports und IDs.
- Die v0.0.1-Fixtures bleiben unverändert und grün; alte Reports bleiben lesbar.

## Echtes NRW: wo die Annahmen abweichen

Die unveränderte [`schuldaten.csv`](../../../examples/schulen_de/real_nrw/schuldaten.csv)
liegt separat neben den synthetischen Daten. Der amtliche
[Datensatzkatalog](https://data.gov.de/suche/daten/schulgrunddaten-nrw?ids=651a0ec7-0e61-4219-b4a7-ffcfbb7b15b0)
weist die Lizenz dl-de/by-2-0 aus. Abrufzeit, Attribution und Hash stehen in
[`provenance.json`](../../../examples/schulen_de/real_nrw/provenance.json).

| Merkmal | Synthetisches NRW | Echter Download |
|---|---|---|
| Zeilen / benannte Spalten | 8 / 12 | 5.646 / 24 |
| Encoding / Trennzeichen | UTF-8 / Semikolon | UTF-8 / Semikolon |
| Dateianfang | direkt Header | zusätzliche `sep=;`-Zeile |
| Kopfzeile | vollständig benannt | unbenutztes leeres Feld am Ende |
| Schulname | eine Spalte | drei Namensspalten plus Kurzbezeichnung |
| Schulform | lesbarer Text | 26 Codes, z. B. `02`, `20`, `0A` |
| Rechtsform | öffentlich/privat | Codes `1` und `2` |
| Straße/Hausnummer | getrennt | gemeinsam in `Strasse` |
| Koordinaten | Dezimalkomma | ganzzahlige Zeichenfolgen in UTM-Spalten |
| CRS | nicht deklariert | 5.405 × EPSG:25832; 241 × Text `null` |
| Schulbetrieb | nicht modelliert | sieben Status-Codes plus Betriebsdatum |

Der Katalog nennt Gauß-Krüger, die Datei deklariert EPSG:25832. Dieser Widerspruch
wird dokumentiert; Zahlenranges sind kein Beweis für ein CRS. Der Text `null`
bleibt Rohwert. Es gibt keine stille Konvertierung zu Python-None.

Eine unabhängige Standard-CSV-Lesung stimmt für **alle 5.646 Zeilen und 24
Spalten** mit der Engine überein; Schulnummern sind im Snapshot eindeutig. Der
Vergleich fand sechs falsch gelesene Namenszellen: Der CSV-Sniffer schloss aus
den ersten 8 KiB ohne maskierte Anführungszeichen auf `doublequote=False`.
Standardkonformes Double-Quote-Escaping ist jetzt unabhängig vom kurzen Sample
aktiv und durch einen Regressionstest abgesichert.

Auch die vollständige Inspektionspipeline lief mit Echtdaten und Provenienz.
Die Struktur ist lesbar, die fachliche Codeauflösung aber noch offen: Schulform,
Rechtsform und Betriebsstatus brauchen amtliche Schlüsseltabellen. Die
synthetischen Regeln für ausgeschriebene Schulformen decken diese Codes nicht ab.
Für echte Schulen liegen keine Entity-/Normalisierungslabels vor; es wird keine
semantische Trefferquote für Echtdaten behauptet. Vollständige Strukturdaten:
[`real-nrw-comparison.json`](real-nrw-comparison.json).

## Reproduzieren

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.validation-tmp/reproduce
.\.venv\Scripts\python.exe -m pyright src tests scripts
.\.venv\Scripts\python.exe scripts/benchmark_schulen.py
```

Vollständige Fixture-Reports: `out/schulen_de/`, DuckDB: `out/schulen_de.duckdb`.
Beispielausgabe: [`explain-example.txt`](explain-example.txt).

```powershell
.\.venv\Scripts\python.exe -m marble.cli explain out/schulen_de/report.json --kind normalization --id norm-13630f58201198e6affe
```

Geändert wurden CSV-Ingestion/Profile, additive Pydantic-Verträge und Schemas,
Pipeline-/CLI-Exporte, `schools.py`, `normalization.py`, Schul-Tests,
Entwicklungsabhängigkeiten und Dokumentation. `export_schemas.py` und
`benchmark_schulen.py` machen Schemas und Auswertung erneut erzeugbar.

**Nächster Schritt:** amtliche NRW-Schlüsseltabellen als versioniertes, explizites
Pack aufnehmen und an einem separat handgelabelten Echtdaten-Holdout prüfen.
Ein grünes synthetisches Fixture belegt keine allgemeine Treffergenauigkeit.
