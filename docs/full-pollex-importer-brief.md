# Full POLLEX Register Implementation Brief

## Summary

Build a full local POLLEX-derived synonym register instead of relying on partial CSV,
HTML, or audit-cache input. POLLEX currently reports more than 64,000 reflexes, more
than 5,000 reconstructions, and 67 languages on its live site.

## Key Changes

- Add a full POLLEX importer that crawls reconstruction pages from
  `https://pollex.eva.mpg.de/entry/?page=N`.
- Collect every `/entry/<slug>/`, then fetch
  `https://pollex.eva.mpg.de/api/xml/pollex/<slug>/`.
- Fetch `https://pollex.eva.mpg.de/api/xml/language/` and join `language_id` to
  language name/code.
- Write a canonical local snapshot at
  `reference/pollex-synonym-register/pollex-full-snapshot.json`.
- Preserve protoform, level, reconstruction description, notes, slug, reflex/item,
  reflex description, language ID/name/code, borrowed, flag, source ID, raw row,
  added date, and POLLEX entry ID.
- Update the register builder so it can build from the full snapshot.

## Importer Behavior

- New command:
  `python tools/pollex_full_import.py harvest`
- Use polite crawling: custom User-Agent, timeout, retry with backoff, and a small
  delay between requests.
- Support resume/re-run with an ignored cache under `.cache/pollex/`.
- Parse XML with `xml.etree.ElementTree`.
- Treat a reconstruction as successful when XML contains a protoform and zero or more
  entry resources.
- Log reconstruction pages found, XML files fetched, protoforms parsed, reflex rows
  parsed, skipped slugs, and error slugs.

## Register Behavior

- Keep separate identities for same-spelling English glosses and POLLEX reflexes.
- Store all POLLEX rows, including borrowed/problematic/irregular rows.
- Preserve metadata and filter risky suggestions at suggestion time.
- Add `--include-flagged` to `suggest` to show borrowed/problematic/irregular
  alternatives separately.

## Test Plan

- Existing register unit tests must pass.
- Add importer tests with saved minimal XML fixtures for:
  - one protoform with multiple reflex rows,
  - empty-entry protoform,
  - borrowed row,
  - flagged row,
  - language ID join.
- Add a small integration dry-run against a short slug list such as `-a`, `kau.2b`,
  and `mana.1` where available.
- Acceptance check: full harvest produces thousands of protoforms and tens of
  thousands of reflex rows, and `lookup mana` still separates English gloss and
  POLLEX reflex entries.

## Assumptions

- The live POLLEX XML API is the source of truth.
- Generated POLLEX snapshots are not committed by default until data licensing and
  redistribution expectations are confirmed.
- Tool code is MIT licensed; POLLEX data requires POLLEX citation.
