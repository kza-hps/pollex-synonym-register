# POLLEX Synonym Register

A small Python tool for building a bidirectional editorial register from POLLEX rows:

- English gloss -> Polynesian reflex forms
- Polynesian reflex form -> English glosses

The goal is to help writers, editors, and researchers check whether a proposed noun,
verb, or key descriptive term has POLLEX-backed support before using it in a
Polynesian-language-informed text.

## Status

This repository contains the reusable tool code only. It does not bundle POLLEX data,
manuscript text, audit files, or generated register snapshots.

POLLEX data should be fetched from POLLEX-Online and cited appropriately:

Greenhill SJ & Clark R. 2011. POLLEX-Online: The Polynesian Lexicon Project Online.
Oceanic Linguistics, 50(2), 551-559.

POLLEX-Online: https://pollex.eva.mpg.de/

## Usage

Run the built-in tests:

```bash
python tools/pollex_synonym_register.py test
```

Build from a CSV:

```bash
python tools/pollex_synonym_register.py build --csv rows.csv
```

Build from a copied POLLEX HTML table:

```bash
python tools/pollex_synonym_register.py build --html pollex-page.html
```

Look up a word or reflex:

```bash
python tools/pollex_synonym_register.py lookup company
python tools/pollex_synonym_register.py lookup Kau
```

Suggest non-problematic alternatives:

```bash
python tools/pollex_synonym_register.py suggest authority
```

Generated files are written under:

```text
reference/pollex-synonym-register/
```

Those generated data files are ignored by default in this public tool repo.

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

The register deliberately separates entries by both term and kind, so the same spelling
can exist as both:

- an `english_gloss`
- a `pollex_reflex`

This avoids corrupting entries such as `Mana`, which can appear both as a gloss word
and as an attested reflex form.

## Full POLLEX Importer

The next planned step is a full XML-based POLLEX importer. See:

```text
docs/full-pollex-importer-brief.md
```

## License

Code in this repository is licensed under the MIT License. POLLEX data is not included
and remains governed by POLLEX-Online's own terms and citation requirements.
