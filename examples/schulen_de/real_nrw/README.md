# Tatsächliche NRW-Schulgrunddaten

`schuldaten.csv` ist der unveränderte Download vom 01.11.2026, 23:30 Uhr
Europe/Berlin. Herausgeber: Ministerium für Schule und Bildung des Landes
Nordrhein-Westfalen. Lizenz: **Datenlizenz Deutschland – Namensnennung 2.0**
([Lizenztext](https://www.govdata.de/dl-de/by-2-0)).

Quelle: [amtlicher Datensatzkatalog](https://data.gov.de/suche/daten/schulgrunddaten-nrw?ids=651a0ec7-0e61-4219-b4a7-ffcfbb7b15b0),
[CSV des Schulministeriums](https://www.schulministerium.nrw.de/BiPo/OpenData/Schuldaten/schuldaten.csv).
Der Download leitet auf `apps.schulministerium.nrw.de` weiter.

`provenance.json` dokumentiert Abrufzeit, Last-Modified, Lizenz, Herausgeber und
SHA-256. `source_metadata.json` kann über `--source-metadata` eingelesen werden.
Die CSV wurde nicht verändert, bereinigt oder gefiltert.

5.646 Datensätze, 24 benannte Spalten, UTF-8, Semikolon, `sep=;`-Vorlaufzeile und
eine unbenutzte leere Kopfspalte. 5.405 Zeilen deklarieren `EPSG:25832`, 241
enthalten im EPSG-Feld den Text `null`. Die Katalogbeschreibung erwähnt dagegen
Gauß-Krüger. Es wird kein CRS geraten und keine Transformation vorgenommen.

Es gibt noch keine gelabelten Entity-/Normalisierungsziele für diese Echtdaten.
Der Lauf prüft Ingestion und Rohwerterhalt, keine semantische Trefferquote.
Siehe [Auswertung](../../../docs/validation/schulen_de/RESULTS.md).
