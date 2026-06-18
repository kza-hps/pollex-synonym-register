# Full POLLEX Importer Notes

## Summary

`tools/pollex_full_import.py` builds a full local POLLEX-derived snapshot for the
synonym register.

The importer:

- Crawls reconstruction slugs from `https://pollex.eva.mpg.de/entry/?page=N`.
- Fetches each reconstruction through
  `https://pollex.eva.mpg.de/api/xml/pollex/<slug>/`.
- Parses protoform metadata and reflex rows from the XML response.
- Preserves language name/code from the `_language_cache` embedded in each row.
- Writes a normalized snapshot to
  `reference/pollex-synonym-register/pollex-full-snapshot.json`.

## Commands

Harvest the full corpus:

```bash
python tools/pollex_full_import.py harvest
```

Refresh the slug list before harvesting:

```bash
python tools/pollex_full_import.py harvest --refresh-slugs
```

Run unit tests:

```bash
python tools/pollex_full_import.py test
```

Run the optional live network test:

```bash
python tools/pollex_full_import.py test --live
```

## Importer Behavior

- Uses a custom User-Agent, request timeout, retries, backoff, and delay between
  uncached requests.
- Caches raw XML under `.cache/pollex/xml/` so interrupted harvests can resume.
- Treats XML with a protoform and zero or more reflex resources as a successful
  reconstruction.
- Records skipped slugs, fetch errors, total protoforms, and total reflex rows in
  the snapshot `meta` block.

## Register Behavior

`tools/pollex_synonym_register.py build` auto-detects the full snapshot and uses it
as the default source when present.

The register:

- Keeps separate identities for same-spelling English glosses and POLLEX reflexes.
- Stores clean, borrowed, problematic, and phonologically irregular rows.
- Filters risky suggestions at suggestion time.
- Supports `--include-flagged` to show borrowed/problematic/irregular alternatives
  in a separate review section.

## Data Boundary

Generated POLLEX-derived snapshots and registers are ignored by default in this
public repo. The MIT license applies to tool code only; POLLEX-derived data should
be handled with POLLEX-Online citation and redistribution expectations in mind.
