#!/usr/bin/env python3
"""
POLLEX Bidirectional Synonym Register

Standalone builder and lookup tool. Maps English gloss words <-> POLLEX reflexes.
Independent of any manuscript or editorial project.

Commands:
  build    Build/update the register from source inputs
  lookup   Look up a word (English or POLLEX reflex)
  suggest  Return non-problematic alternatives
  test     Run built-in unit tests

Usage:
  python tools/pollex_synonym_register.py build
  python tools/pollex_synonym_register.py build --cache pollex-term-cache.json
  python tools/pollex_synonym_register.py build --csv my-terms.csv --html page.html
  python tools/pollex_synonym_register.py lookup company
  python tools/pollex_synonym_register.py lookup Kau
  python tools/pollex_synonym_register.py suggest company
  python tools/pollex_synonym_register.py test
"""
from __future__ import annotations

import argparse
import csv
import html as html_module
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER_DIR = ROOT / "reference" / "pollex-synonym-register"
REGISTER_JSON = REGISTER_DIR / "register.json"
REGISTER_MD = REGISTER_DIR / "register.md"
DEFAULT_CACHE = ROOT / "pollex-term-cache.json"

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "almost",
    "along", "also", "always", "am", "an", "and", "any", "are", "around",
    "as", "at", "away", "back", "be", "been", "before", "being", "below",
    "beneath", "beside", "between", "beyond", "both", "but", "by", "came",
    "can", "cf", "could", "did", "do", "does", "down", "each", "etc",
    "even", "ever", "every", "for", "form", "forms", "from", "had", "has",
    "have", "he", "her", "here", "hers", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "like", "made", "make",
    "many", "me", "more", "most", "much", "my", "never", "no", "nor",
    "not", "now", "of", "off", "on", "once", "one", "only", "or", "other",
    "our", "out", "over", "own", "said", "same", "se", "see", "she",
    "should", "so", "some", "still", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those",
    "though", "through", "to", "too", "under", "until", "up", "upon",
    "use", "used", "us", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "will", "with", "without", "would", "you",
    "your",
}

POLLEX_FLAG_STRINGS = [
    "Phonologically Irregular",
    "Problematic",
]

ASCII_WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def make_entry_id(kind: str, term: str) -> str:
    return f"{kind}:{term.lower()}"


def make_source_id(language: str, reconstruction: str, reflex: str, description: str) -> str:
    return f"{language.lower().replace(' ', '-')}|{reconstruction}|{reflex}|{description}"


def detect_flags(description: str) -> tuple[str, list[str]]:
    """Strip inline POLLEX flags from description text; return (cleaned, flags)."""
    flags: list[str] = []
    for flag_str in POLLEX_FLAG_STRINGS:
        if flag_str in description:
            flags.append(flag_str.lower().replace(" ", "_"))
            description = description.replace(flag_str, "")
    description = re.sub(r"\s{2,}", " ", description).strip().rstrip(",; ")
    return description, flags


def parse_english_terms(description: str) -> list[str]:
    """Extract usable English content words and short phrases from a description."""
    seen: dict[str, str] = {}  # lowercase -> first-seen form

    # Split on commas and semicolons to get candidate phrases
    chunks = re.split(r"[,;]", description)
    for chunk in chunks:
        chunk = chunk.strip().strip(".'\"()[]{}")
        if not chunk:
            continue
        words = ASCII_WORD_RE.findall(chunk)
        content = [w for w in words if w.lower() not in STOPWORDS and len(w) >= 3 and w.isascii()]
        if not content:
            continue
        # Short phrase (1-3 content words) -> keep as phrase term
        if len(content) <= 3:
            phrase = " ".join(content)
            lower = phrase.lower()
            if lower not in seen:
                seen[lower] = phrase

    # Also extract all individual content words from the full description
    for word in ASCII_WORD_RE.findall(description):
        if word.lower() not in STOPWORDS and len(word) >= 3 and word.isascii():
            lower = word.lower()
            if lower not in seen:
                seen[lower] = word

    return list(seen.values())


class Register:
    def __init__(self) -> None:
        self.sources: dict[str, dict] = {}
        self.entries: dict[str, dict] = {}
        self._term_index: dict[str, list[str]] = {}  # lowercase -> entry ids

    def _entry_id(self, term: str, kind: str) -> str:
        """Get or create the canonical entry id for a term/kind pair."""
        lower = term.lower()
        entry_id = make_entry_id(kind, term)
        if entry_id in self.entries:
            return entry_id
        if kind == "pollex_reflex":
            display_term = term  # preserve original capitalisation from source
        else:
            display_term = term[0].upper() + term[1:] if term else term
        self.entries[entry_id] = {
            "term": display_term,
            "kind": kind,
            "equivalents": [],
            "equivalent_ids": [],
            "source_ids": [],
        }
        self._term_index.setdefault(lower, []).append(entry_id)
        return entry_id

    def _add_to_entry(
        self, entry_id: str, equivalent_id: str, source_id: str
    ) -> None:
        entry = self.entries[entry_id]
        equivalent = self.entries[equivalent_id]["term"]
        if equivalent_id not in entry["equivalent_ids"]:
            entry["equivalent_ids"].append(equivalent_id)
        if equivalent not in entry["equivalents"]:
            entry["equivalents"].append(equivalent)
        if source_id not in entry["source_ids"]:
            entry["source_ids"].append(source_id)

    def add_row(
        self,
        language: str,
        reconstruction: str,
        reflex: str,
        description: str,
        flags: list[str] | None = None,
    ) -> None:
        clean_desc, detected_flags = detect_flags(description)
        all_flags = sorted(set((flags or []) + detected_flags))
        source_id = make_source_id(language, reconstruction, reflex, clean_desc)

        if source_id not in self.sources:
            self.sources[source_id] = {
                "language": language,
                "reconstruction": reconstruction,
                "reflex": reflex,
                "description": clean_desc,
                "flags": all_flags,
            }

        reflex_id = self._entry_id(reflex, "pollex_reflex")
        english_terms = parse_english_terms(clean_desc)

        for term in english_terms:
            eng_id = self._entry_id(term, "english_gloss")
            self._add_to_entry(eng_id, reflex_id, source_id)
            self._add_to_entry(reflex_id, eng_id, source_id)

    def lookup(self, word: str, kind: str | None = None) -> dict | None:
        entry_ids = self.entry_ids_for(word, kind)
        if not entry_ids:
            return None
        return self.entries.get(entry_ids[0])

    def entry_ids_for(self, word: str, kind: str | None = None) -> list[str]:
        entry_ids = self._term_index.get(word.lower(), [])
        if kind:
            return [eid for eid in entry_ids if self.entries[eid]["kind"] == kind]
        return entry_ids

    def to_dict(self) -> dict:
        return {
            "entries": dict(
                sorted(
                    self.entries.items(),
                    key=lambda kv: (kv[1].get("term", kv[0]).lower(), kv[1]["kind"]),
                )
            ),
            "sources": dict(sorted(self.sources.items())),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Register":
        reg = cls()
        reg.sources = data.get("sources", {})
        reg.entries = data.get("entries", {})
        for entry_id, entry in reg.entries.items():
            entry.setdefault("term", entry_id)
            entry.setdefault("equivalent_ids", [])
            reg._term_index.setdefault(entry["term"].lower(), []).append(entry_id)
        return reg


def load_from_cache(path: Path, register: Register) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for _query_term, result in data.items():
        if result.get("status") != "found":
            continue
        for row in result.get("results", []):
            language = row.get("language", "").strip()
            reconstruction = row.get("reconstruction", "").strip()
            reflex = row.get("reflex", "").strip()
            description = row.get("description", "").strip()
            if not all([language, reflex, description]):
                continue
            register.add_row(language, reconstruction, reflex, description)
            count += 1
    return count


def load_from_csv(path: Path, register: Register) -> int:
    count = 0
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            language = row.get("language", "").strip()
            reconstruction = row.get("reconstruction", "").strip()
            reflex = row.get("reflex", "").strip()
            description = row.get("description", "").strip()
            flags_raw = row.get("flags", "").strip()
            flags = (
                [f.strip().lower() for f in flags_raw.split(",") if f.strip()]
                if flags_raw
                else []
            )
            if not all([language, reflex, description]):
                continue
            register.add_row(language, reconstruction, reflex, description, flags)
            count += 1
    return count


def load_from_html(path: Path, register: Register) -> int:
    page = path.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.I | re.S)
    count = 0
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        clean = []
        for cell in cells[:4]:
            cell = re.sub(r"<[^>]+>", " ", cell)
            cell = html_module.unescape(re.sub(r"\s+", " ", cell)).strip()
            clean.append(cell)
        language, reconstruction, reflex, description = clean
        if not all([language, reflex, description]):
            continue
        register.add_row(language, reconstruction, reflex, description)
        count += 1
    return count


def write_register(register: Register) -> None:
    REGISTER_DIR.mkdir(parents=True, exist_ok=True)
    data = register.to_dict()
    REGISTER_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(data, REGISTER_MD)
    print(f"Written: {REGISTER_JSON}")
    print(f"Written: {REGISTER_MD}")


def _write_markdown(data: dict, path: Path | None = None) -> None:
    dest = path or REGISTER_MD
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# POLLEX Synonym Register",
        "",
        "Bidirectional index: English gloss words and POLLEX reflexes.",
        "Alphabetized. Generated from `tools/pollex_synonym_register.py`.",
        "",
    ]
    current_letter = ""
    for entry_id, entry in sorted(
        data["entries"].items(),
        key=lambda kv: (kv[1].get("term", kv[0]).lower(), kv[1]["kind"]),
    ):
        term = entry.get("term", entry_id)
        first_letter = term[0].upper()
        if first_letter != current_letter:
            current_letter = first_letter
            lines.extend(["", f"## {current_letter}", ""])
        kind_label = (
            "POLLEX reflex" if entry["kind"] == "pollex_reflex" else "English gloss"
        )
        lines.append(f"### {term} *({kind_label})*")
        lines.append("")
        equiv_str = ", ".join(entry["equivalents"]) if entry["equivalents"] else "-"
        lines.append(f"**Equivalents:** {equiv_str}")
        lines.append("")
        lines.append("**Sources:**")
        for sid in entry["source_ids"]:
            src = data["sources"].get(sid, {})
            flag_note = (
                " [" + ", ".join(src["flags"]) + "]" if src.get("flags") else ""
            )
            lines.append(
                f"- {src.get('language', '?')} | {src.get('reconstruction', '?')}"
                f" | {src.get('reflex', '?')} | {src.get('description', '?')}{flag_note}"
            )
        lines.append("")
    dest.write_text("\n".join(lines), encoding="utf-8")


def cmd_build(args: argparse.Namespace) -> None:
    register = Register()
    total = 0

    cache_path = Path(args.cache) if args.cache else (
        DEFAULT_CACHE if DEFAULT_CACHE.exists() else None
    )
    if cache_path:
        if not cache_path.exists():
            print(f"Cache file not found: {cache_path}", file=sys.stderr)
        else:
            n = load_from_cache(cache_path, register)
            print(f"Loaded {n} rows from cache: {cache_path}")
            total += n

    if args.csv:
        n = load_from_csv(Path(args.csv), register)
        print(f"Loaded {n} rows from CSV: {args.csv}")
        total += n

    if args.html:
        n = load_from_html(Path(args.html), register)
        print(f"Loaded {n} rows from HTML: {args.html}")
        total += n

    if total == 0:
        print(
            "No source data loaded. Use --cache, --csv, or --html.", file=sys.stderr
        )
        sys.exit(1)

    write_register(register)
    print(
        f"Register built: {len(register.entries)} entries"
        f" from {len(register.sources)} unique sources."
    )


def _print_entry(key: str, entry: dict, sources: dict) -> None:
    kind_label = "POLLEX reflex" if entry["kind"] == "pollex_reflex" else "English gloss"
    print(f"\n{key}  ({kind_label})")
    print(f"  Equivalents: {', '.join(entry['equivalents']) or '-'}")
    print(f"  Sources ({len(entry['source_ids'])}):")
    for sid in entry["source_ids"]:
        src = sources.get(sid, {})
        flag_note = (
            " [" + ", ".join(src["flags"]) + "]" if src.get("flags") else ""
        )
        print(
            f"    {src.get('language', '?')} | {src.get('reconstruction', '?')}"
            f" | {src.get('reflex', '?')} | {src.get('description', '?')}{flag_note}"
        )


def cmd_lookup(args: argparse.Namespace) -> None:
    if not REGISTER_JSON.exists():
        print(
            "Register not found. Run: python tools/pollex_synonym_register.py build --csv rows.csv",
            file=sys.stderr,
        )
        sys.exit(1)
    data = json.loads(REGISTER_JSON.read_text(encoding="utf-8"))
    register = Register.from_dict(data)

    entry_ids = register.entry_ids_for(args.word)
    if not entry_ids:
        print(f"No entry found for: {args.word!r}")
        return
    for entry_id in entry_ids:
        entry = register.entries[entry_id]
        _print_entry(entry.get("term", entry_id), entry, data["sources"])


def classify_suggestions(entry: dict, entries: dict, sources: dict) -> tuple[list[str], list[str]]:
    supported: list[str] = []
    problematic: list[str] = []

    for equiv_id in entry.get("equivalent_ids", []):
        equiv_entry = entries.get(equiv_id)
        if not equiv_entry:
            continue
        shared_source_ids = set(entry["source_ids"]) & set(equiv_entry["source_ids"])
        if not shared_source_ids:
            continue
        has_clean_source = any(not sources.get(sid, {}).get("flags") for sid in shared_source_ids)
        has_flagged_source = any(sources.get(sid, {}).get("flags") for sid in shared_source_ids)
        equivalent = equiv_entry.get("term", equiv_id)
        if has_clean_source:
            supported.append(equivalent)
        elif has_flagged_source:
            problematic.append(equivalent)

    return supported, problematic


def cmd_suggest(args: argparse.Namespace) -> None:
    if not REGISTER_JSON.exists():
        print(
            "Register not found. Run: python tools/pollex_synonym_register.py build --csv rows.csv",
            file=sys.stderr,
        )
        sys.exit(1)
    data = json.loads(REGISTER_JSON.read_text(encoding="utf-8"))
    register = Register.from_dict(data)

    entry_ids = register.entry_ids_for(args.word)
    if not entry_ids:
        print(f"No entry found for: {args.word!r}")
        return

    for entry_id in entry_ids:
        entry = register.entries[entry_id]
        kind_label = "POLLEX reflex" if entry["kind"] == "pollex_reflex" else "English gloss"
        supported, problematic = classify_suggestions(entry, register.entries, data["sources"])

        print(f"\nSuggestions for {entry.get('term', entry_id)!r} ({kind_label}):")
        if supported:
            print(f"  Supported: {', '.join(supported)}")
        else:
            print("  No non-problematic alternatives found.")
        if problematic:
            print(f"  Problematic (author/editor review required): {', '.join(problematic)}")


def run_tests() -> None:
    print("Running unit tests...")
    failures = 0

    def check(condition: bool, label: str) -> None:
        nonlocal failures
        if condition:
            print(f"PASS: {label}")
        else:
            print(f"FAIL: {label}")
            failures += 1

    # --- Build a minimal register from one test row ---
    reg = Register()
    reg.add_row(
        language="New Zealand Maori",
        reconstruction="PN.KAU.2B",
        reflex="Kau",
        description="Multitude, company",
    )

    source_id = "new-zealand-maori|PN.KAU.2B|Kau|Multitude, company"

    # Test 1: Company -> Kau
    entry = reg.lookup("Company")
    check(entry is not None, "Company entry exists")
    check(entry is not None and entry["kind"] == "english_gloss", "Company kind == english_gloss")
    check(entry is not None and "Kau" in entry["equivalents"], "Company -> Kau")

    # Test 2: Kau -> Multitude, company
    entry = reg.lookup("Kau")
    check(entry is not None, "Kau entry exists")
    check(entry is not None and entry["kind"] == "pollex_reflex", "Kau kind == pollex_reflex")
    if entry:
        equivs_lower = [e.lower() for e in entry["equivalents"]]
        check("multitude" in equivs_lower, "Kau -> Multitude")
        check("company" in equivs_lower, "Kau -> company")

    # Test 3: Multitude -> Kau
    entry = reg.lookup("Multitude")
    check(entry is not None, "Multitude entry exists")
    check(entry is not None and "Kau" in entry["equivalents"], "Multitude -> Kau")

    # Test 4: Source metadata attached to all three entries
    for word in ["Company", "Kau", "Multitude"]:
        entry = reg.lookup(word)
        check(
            entry is not None and source_id in entry["source_ids"],
            f"Source id attached to {word}",
        )
    check(source_id in reg.sources, "Source row stored in sources dict")
    src = reg.sources.get(source_id, {})
    check(src.get("language") == "New Zealand Maori", "Source language correct")
    check(src.get("reflex") == "Kau", "Source reflex correct")
    check(src.get("description") == "Multitude, company", "Source description correct")

    # Test 5: Case-insensitive lookup
    for variant in ["company", "Company", "COMPANY"]:
        entry = reg.lookup(variant)
        check(
            entry is not None and "Kau" in entry["equivalents"],
            f"Case-insensitive lookup: {variant!r} -> Kau",
        )

    # Test 6: Problematic metadata
    reg2 = Register()
    reg2.add_row(
        language="Test Language",
        reconstruction="PN.TEST",
        reflex="Testword",
        description="Virtual absence, dearth, scarcity Phonologically Irregular",
    )
    entry = reg2.lookup("absence")
    check(entry is not None, "Problematic row appears in lookup")
    if entry:
        check("Testword" in entry["equivalents"], "Testword in absence equivalents")
    sid2 = list(entry["source_ids"])[0] if entry else ""
    src2 = reg2.sources.get(sid2, {})
    check("phonologically_irregular" in src2.get("flags", []), "Phonologically Irregular detected as flag")
    check("Irregular" not in src2.get("description", ""), "Flag stripped from description")

    # Test 7: Alphabetical order
    data = reg.to_dict()
    sort_keys = [
        (entry.get("term", entry_id).lower(), entry["kind"])
        for entry_id, entry in data["entries"].items()
    ]
    check(sort_keys == sorted(sort_keys), "Entries are alphabetically ordered")

    # Test 8: Markdown output alphabetized and includes source metadata
    import tempfile, os as _os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as _tmp:
        _tmp_path = Path(_tmp.name)
    try:
        _write_markdown(data, _tmp_path)
        md_text = _tmp_path.read_text(encoding="utf-8")
        check("Kau" in md_text, "Kau appears in markdown")
        check("New Zealand Maori" in md_text, "Source language in markdown")
        check("PN.KAU.2B" in md_text, "Reconstruction in markdown")
    finally:
        _os.unlink(_tmp_path)

    # Test 9: CSV input loading
    csv_content = "language,reconstruction,reflex,description\nTongan,PN.AWA,Ava,Gap opening passage\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        tmp.write(csv_content)
        tmp_path = Path(tmp.name)
    try:
        reg3 = Register()
        n = load_from_csv(tmp_path, reg3)
        check(n == 1, "CSV: one row loaded")
        entry = reg3.lookup("gap")
        check(entry is not None and "Ava" in entry["equivalents"], "CSV: Gap -> Ava")
    finally:
        _os.unlink(tmp_path)

    # Test 10: Same spelling can exist as both English gloss and POLLEX reflex
    reg4 = Register()
    reg4.add_row(
        language="Collision Language",
        reconstruction="PN.FOO",
        reflex="Foo",
        description="foo, company",
    )
    foo_ids = reg4.entry_ids_for("foo")
    check(len(foo_ids) == 2, "Same spelling keeps separate gloss/reflex entries")
    foo_gloss = reg4.lookup("foo", "english_gloss")
    foo_reflex = reg4.lookup("foo", "pollex_reflex")
    check(foo_gloss is not None and foo_gloss["kind"] == "english_gloss", "Collision gloss lookup")
    check(foo_reflex is not None and foo_reflex["kind"] == "pollex_reflex", "Collision reflex lookup")
    check(
        foo_gloss is not None and foo_reflex is not None
        and foo_gloss["source_ids"] == foo_reflex["source_ids"],
        "Collision entries retain shared source metadata",
    )

    # Test 11: Suggestions are flagged by the shared source row, not the whole equivalent
    reg5 = Register()
    reg5.add_row(
        language="Clean Language",
        reconstruction="OC.MANA.1",
        reflex="Mana",
        description="Authority, power",
    )
    reg5.add_row(
        language="Problem Language",
        reconstruction="NP.MANA-QAKI",
        reflex="Mana",
        description="Charm Problematic",
    )
    data5 = reg5.to_dict()
    authority = reg5.lookup("authority", "english_gloss")
    charm = reg5.lookup("charm", "english_gloss")
    if authority:
        supported, problematic = classify_suggestions(authority, data5["entries"], data5["sources"])
        check("Mana" in supported, "Clean shared source keeps Mana supported for authority")
        check("Mana" not in problematic, "Unrelated problematic Mana source does not poison authority")
    else:
        check(False, "Authority fixture exists")
    if charm:
        supported, problematic = classify_suggestions(charm, data5["entries"], data5["sources"])
        check("Mana" in problematic, "Flagged shared source marks Mana problematic for charm")
        check("Mana" not in supported, "Problematic-only shared source is not supported")
    else:
        check(False, "Charm fixture exists")

    print()
    if failures == 0:
        print(f"All tests passed.")
    else:
        print(f"{failures} test(s) FAILED.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="POLLEX Bidirectional Synonym Register - builder and lookup tool."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build", help="Build/update the register from source inputs.")
    build_p.add_argument(
        "--cache",
        metavar="PATH",
        help="POLLEX cache JSON (optional; JSON map of query terms to POLLEX result rows)",
    )
    build_p.add_argument(
        "--csv",
        metavar="PATH",
        help="CSV with columns: language, reconstruction, reflex, description [, flags]",
    )
    build_p.add_argument(
        "--html",
        metavar="PATH",
        help="HTML file containing a POLLEX results table",
    )

    lookup_p = sub.add_parser("lookup", help="Look up a word in the register.")
    lookup_p.add_argument("word", help="English word or POLLEX reflex to look up")

    suggest_p = sub.add_parser(
        "suggest", help="Suggest non-problematic reflex-backed alternatives."
    )
    suggest_p.add_argument(
        "word", help="English word or POLLEX reflex to suggest alternatives for"
    )

    sub.add_parser("test", help="Run built-in unit tests.")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = parser.parse_args()

    if args.command == "build":
        cmd_build(args)
    elif args.command == "lookup":
        cmd_lookup(args)
    elif args.command == "suggest":
        cmd_suggest(args)
    elif args.command == "test":
        run_tests()


if __name__ == "__main__":
    main()
