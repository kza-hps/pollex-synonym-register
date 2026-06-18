# POLLEX Synonym Register

A standalone Python tool for building a bidirectional editorial register from
POLLEX-Online rows:

- English gloss -> Polynesian reflex forms
- Polynesian reflex form -> English glosses

It is designed for writers, editors, and researchers who want to check whether a
proposed noun, verb, or key descriptive term has POLLEX-backed support before
using it in Polynesian-language-informed text.

## Status

The repository contains reusable MIT-licensed tool code. It can harvest the live
POLLEX XML corpus into a local snapshot, then build a local synonym register from
that snapshot.

Generated POLLEX-derived data files are ignored by default:

```text
reference/pollex-synonym-register/pollex-full-snapshot.json
reference/pollex-synonym-register/register.json
reference/pollex-synonym-register/register.md
```

POLLEX data should be fetched from POLLEX-Online and cited appropriately:

Greenhill SJ & Clark R. 2011. POLLEX-Online: The Polynesian Lexicon Project
Online. Oceanic Linguistics, 50(2), 551-559.

POLLEX-Online: https://pollex.eva.mpg.de/

## Quick Start

Run the built-in tests:

```bash
python tools/pollex_synonym_register.py test
python tools/pollex_full_import.py test
```

Harvest the full POLLEX XML corpus:

```bash
python tools/pollex_full_import.py harvest
```

The harvest is resumable. Raw XML is cached under `.cache/pollex/`; the normalized
snapshot is written to:

```text
reference/pollex-synonym-register/pollex-full-snapshot.json
```

Build the register from the snapshot:

```bash
python tools/pollex_synonym_register.py build
```

Look up a word or reflex:

```bash
python tools/pollex_synonym_register.py lookup company
python tools/pollex_synonym_register.py lookup Kau
```

Suggest non-problematic alternatives:

```bash
python tools/pollex_synonym_register.py suggest authority
python tools/pollex_synonym_register.py suggest company --include-flagged
```

## Other Build Sources

Build from a CSV:

```bash
python tools/pollex_synonym_register.py build --csv rows.csv
```

Build from a copied POLLEX HTML table:

```bash
python tools/pollex_synonym_register.py build --html pollex-page.html
```

Build from an explicit snapshot:

```bash
python tools/pollex_synonym_register.py build --snapshot reference/pollex-synonym-register/pollex-full-snapshot.json
```

## CSV Input Format

```csv
language,reconstruction,reflex,description,flags
New Zealand Maori,PN.KAU.2B,Kau,"Multitude, company",
Tahitian,EP.KORE-GA,Ore/raa,"Virtual absence dearth scarcity",phonologically_irregular
```

Required columns:

- `language`
- `reconstruction`
- `reflex`
- `description`

Optional:

- `flags`, comma-separated

## Data Model

The register deliberately separates entries by both term and kind, so the same
spelling can exist as both:

- an `english_gloss`
- a `pollex_reflex`

This avoids corrupting entries such as `Mana`, which can appear both as a gloss
word and as an attested reflex form.

Suggestions hide borrowed, problematic, and phonologically irregular rows by
default. Pass `--include-flagged` to show them in a separate author/editor review
section.

## License

Code in this repository is licensed under the MIT License. POLLEX data is not
included and remains governed by POLLEX-Online's own terms and citation
requirements.
