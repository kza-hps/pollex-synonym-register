#!/usr/bin/env python3
"""
pollex_full_import.py — Full POLLEX snapshot harvester.

Crawls the POLLEX XML API to build a complete local snapshot of all
reconstructions and reflex rows, then writes pollex-full-snapshot.json
that pollex_synonym_register.py uses by default.

Usage:
  python tools/pollex_full_import.py harvest
  python tools/pollex_full_import.py harvest --delay 0.2 --limit 50
  python tools/pollex_full_import.py harvest --refresh-slugs
  python tools/pollex_full_import.py test
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER_DIR = ROOT / "reference" / "pollex-synonym-register"
CACHE_DIR = ROOT / ".cache" / "pollex"
DEFAULT_SNAPSHOT = REGISTER_DIR / "pollex-full-snapshot.json"

POLLEX_BASE = "https://pollex.eva.mpg.de"
ENTRY_INDEX_URL = f"{POLLEX_BASE}/entry/"
XML_POLLEX_URL = f"{POLLEX_BASE}/api/xml/pollex/"

USER_AGENT = "Mozilla/5.0 (POLLEX synonym register research)"

FLAG_MAP = {
    "P": "problematic",
    "I": "phonologically_irregular",
}


def _ssl_ctx() -> ssl.SSLContext:
    return ssl._create_unverified_context()


def fetch_url(url: str, timeout: int = 25, retries: int = 3, backoff: float = 2.0) -> str:
    """Fetch a URL with retries. Raises on final failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = _ssl_ctx()
    last_exc: Exception = RuntimeError("no attempts made")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last_exc


def crawl_slug_list(delay: float = 0.3) -> list[str]:
    """Page through the POLLEX reconstruction index and return all unique slugs."""
    slugs: dict[str, None] = {}
    page = 1
    while True:
        url = f"{ENTRY_INDEX_URL}?page={page}"
        try:
            html = fetch_url(url)
        except Exception as exc:
            print(f"  Stopping at page {page}: {exc}", file=sys.stderr)
            break
        found = list(dict.fromkeys(re.findall(r"/entry/([^/\"'?#\s]+)/", html)))
        found = [s for s in found if s and not s.startswith("?") and "page" not in s]
        new = [s for s in found if s not in slugs]
        if not new:
            break
        for s in found:
            slugs[s] = None
        print(f"  Page {page}: {len(found)} slugs, {len(new)} new (total {len(slugs)})")
        page += 1
        time.sleep(delay)
    return list(slugs)


def fetch_xml_for_slug(
    slug: str, cache_dir: Path, delay: float = 0.15
) -> str | None:
    """Return cached XML for slug, fetching and caching if not yet stored."""
    xml_path = cache_dir / "xml" / f"{slug}.xml"
    if xml_path.exists():
        return xml_path.read_text(encoding="utf-8", errors="replace")
    url = f"{XML_POLLEX_URL}{urllib.parse.quote(slug, safe='.-')}/"
    try:
        raw = fetch_url(url)
    except Exception as exc:
        print(f"  Error fetching {slug!r}: {exc}", file=sys.stderr)
        return None
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    xml_path.write_text(raw, encoding="utf-8")
    time.sleep(delay)
    return raw


def _text(el: ET.Element | None, tag: str, default: str = "") -> str:
    if el is None:
        return default
    val = el.findtext(tag) or ""
    return val.strip()


def parse_entry_xml(raw: str) -> dict | None:
    """
    Parse one POLLEX reconstruction XML into a protoform dict.

    Returns None if the XML is missing a protoform element (empty entry).
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None

    pf_el = root.find("protoform")
    if pf_el is None:
        return None

    protoform = _text(pf_el, "protoform")
    if not protoform:
        return None

    proto: dict = {
        "protoform": protoform,
        "slug": _text(pf_el, "slug"),
        "level": _text(pf_el, "level"),
        "description": _text(pf_el, "description"),
        "notes": _text(pf_el, "notes"),
        "reflexes": [],
    }

    entries_el = root.find("entries")
    if entries_el is None or len(entries_el) == 0:
        return proto

    for res in entries_el.findall("resource"):
        lang_el = res.find("_language_cache")
        language = _text(lang_el, "language")
        language_code = _text(lang_el, "pollexcode")

        src_el = res.find("_source_cache")
        source = _text(src_el, "source")

        flag_raw = _text(res, "flag")
        if flag_raw.lower() in ("none", ""):
            flag_raw = ""

        borrowed_raw = _text(res, "borrowed", "False")
        borrowed = borrowed_raw.lower() == "true"

        proto["reflexes"].append(
            {
                "id": _as_int(res.findtext("id")),
                "language_id": _as_int(res.findtext("language_id")),
                "language": language,
                "language_code": language_code,
                "item": _text(res, "item"),
                "description": _text(res, "description"),
                "borrowed": borrowed,
                "flag": flag_raw,
                "source_id": _as_int(res.findtext("source_id")),
                "source": source,
                "raw": _text(res, "raw"),
                "added": _text(res, "added"),
            }
        )

    return proto


def _as_int(text: str | None) -> int | None:
    try:
        return int(text) if text else None
    except (ValueError, TypeError):
        return None


def harvest(
    out: Path,
    cache_dir: Path,
    delay: float = 0.15,
    limit: int | None = None,
    refresh_slugs: bool = False,
) -> None:
    print("Step 1: Slug list")
    slug_cache = cache_dir / "slugs.json"
    if slug_cache.exists() and not refresh_slugs:
        slugs: list[str] = json.loads(slug_cache.read_text(encoding="utf-8"))
        print(f"  Loaded {len(slugs)} slugs from {slug_cache}")
    else:
        print("  Crawling POLLEX reconstruction index...")
        slugs = crawl_slug_list(delay=delay)
        slug_cache.parent.mkdir(parents=True, exist_ok=True)
        slug_cache.write_text(
            json.dumps(slugs, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  Saved {len(slugs)} slugs to {slug_cache}")

    if limit:
        slugs = slugs[:limit]
        print(f"  Limited to first {limit} slugs.")

    already_cached = sum(
        1 for s in slugs if (cache_dir / "xml" / f"{s}.xml").exists()
    )
    print(
        f"\nStep 2: Fetching XML ({len(slugs)} total, "
        f"{already_cached} cached, {len(slugs) - already_cached} to fetch)"
    )

    protoforms: list[dict] = []
    errors = 0
    skipped_no_protoform = 0

    for i, slug in enumerate(slugs, 1):
        raw = fetch_xml_for_slug(slug, cache_dir, delay=delay)
        if not raw:
            errors += 1
            continue
        proto = parse_entry_xml(raw)
        if proto is None:
            skipped_no_protoform += 1
            continue
        protoforms.append(proto)
        if i % 250 == 0 or i == len(slugs):
            last = f"{proto['level']}.{proto['protoform']}"
            reflexes_so_far = sum(len(p["reflexes"]) for p in protoforms)
            print(f"  [{i}/{len(slugs)}] {last:<30} ({reflexes_so_far:,} reflexes so far)")

    total_reflexes = sum(len(p["reflexes"]) for p in protoforms)
    snapshot = {
        "meta": {
            "harvested_at": datetime.now(timezone.utc).isoformat(),
            "source_url": POLLEX_BASE,
            "total_protoforms": len(protoforms),
            "total_reflex_rows": total_reflexes,
            "slugs_attempted": len(slugs),
            "skipped_no_protoform": skipped_no_protoform,
            "fetch_errors": errors,
        },
        "protoforms": protoforms,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    size_mb = out.stat().st_size / 1_048_576
    print(f"\nSnapshot written: {out}")
    print(f"  {len(protoforms):,} protoforms, {total_reflexes:,} reflex rows")
    print(f"  Skipped (no protoform): {skipped_no_protoform}  Errors: {errors}")
    print(f"  File size: {size_mb:.1f} MB")


# ---------------------------------------------------------------------------
# Fixtures for unit tests
# ---------------------------------------------------------------------------

FIXTURE_BASIC = """\
<?xml version="1.0" encoding="utf-8"?>
<response>
 <protoform>
  <protoform>KAU.2B</protoform>
  <slug>kau.2b</slug>
  <level>PN</level>
  <description>Group of people, company</description>
  <notes></notes>
 </protoform>
 <entries>
  <resource>
   <id>79007</id>
   <language_id>12</language_id>
   <item>Kau</item>
   <description>Multitude, company</description>
   <borrowed>False</borrowed>
   <flag></flag>
   <source_id>25</source_id>
   <raw></raw>
   <added>2022-07-30</added>
   <_language_cache>
    <language>New Zealand Maori</language>
    <pollexcode>NZM</pollexcode>
   </_language_cache>
   <_source_cache>
    <source>Biggs 1990</source>
   </_source_cache>
  </resource>
  <resource>
   <id>14618</id>
   <language_id>42</language_id>
   <item>Kau</item>
   <description>Collective prefix</description>
   <borrowed>False</borrowed>
   <flag>None</flag>
   <source_id>43</source_id>
   <raw></raw>
   <added>2010-09-21</added>
   <_language_cache>
    <language>East Futuna</language>
    <pollexcode>EFU</pollexcode>
   </_language_cache>
   <_source_cache>
    <source>Moyse-Faurie 1993</source>
   </_source_cache>
  </resource>
 </entries>
</response>"""

FIXTURE_EMPTY_ENTRIES = """\
<?xml version="1.0" encoding="utf-8"?>
<response>
 <protoform>
  <protoform>FOO.1</protoform>
  <slug>foo.1</slug>
  <level>MP</level>
  <description>Test empty</description>
  <notes></notes>
 </protoform>
 <entries></entries>
</response>"""

FIXTURE_NO_PROTOFORM = """\
<?xml version="1.0" encoding="utf-8"?>
<response>
 <entries></entries>
</response>"""

FIXTURE_BORROWED = """\
<?xml version="1.0" encoding="utf-8"?>
<response>
 <protoform>
  <protoform>SWORD</protoform>
  <slug>sword</slug>
  <level>NP</level>
  <description>Sword (borrowed)</description>
  <notes></notes>
 </protoform>
 <entries>
  <resource>
   <id>1</id>
   <language_id>1</language_id>
   <item>Soo</item>
   <description>Sword</description>
   <borrowed>True</borrowed>
   <flag></flag>
   <source_id>1</source_id>
   <raw></raw>
   <added>2020-01-01</added>
   <_language_cache>
    <language>Tongan</language>
    <pollexcode>TON</pollexcode>
   </_language_cache>
   <_source_cache><source>Test 2020</source></_source_cache>
  </resource>
 </entries>
</response>"""

FIXTURE_FLAGGED = """\
<?xml version="1.0" encoding="utf-8"?>
<response>
 <protoform>
  <protoform>MANA.1</protoform>
  <slug>mana.1</slug>
  <level>OC</level>
  <description>Spiritual power, authority</description>
  <notes></notes>
 </protoform>
 <entries>
  <resource>
   <id>100</id>
   <language_id>5</language_id>
   <item>Mana</item>
   <description>Authority, power</description>
   <borrowed>False</borrowed>
   <flag></flag>
   <source_id>5</source_id>
   <raw></raw>
   <added>2010-01-01</added>
   <_language_cache>
    <language>Maori</language>
    <pollexcode>NZM</pollexcode>
   </_language_cache>
   <_source_cache><source>Williams 1971</source></_source_cache>
  </resource>
  <resource>
   <id>101</id>
   <language_id>6</language_id>
   <item>Mana</item>
   <description>Charm, luck</description>
   <borrowed>False</borrowed>
   <flag>P</flag>
   <source_id>6</source_id>
   <raw></raw>
   <added>2010-01-01</added>
   <_language_cache>
    <language>Rennellese</language>
    <pollexcode>REN</pollexcode>
   </_language_cache>
   <_source_cache><source>Elbert 1975</source></_source_cache>
  </resource>
  <resource>
   <id>102</id>
   <language_id>7</language_id>
   <item>Mana</item>
   <description>Prestige</description>
   <borrowed>False</borrowed>
   <flag>I</flag>
   <source_id>7</source_id>
   <raw></raw>
   <added>2010-01-01</added>
   <_language_cache>
    <language>Tahitian</language>
    <pollexcode>TAH</pollexcode>
   </_language_cache>
   <_source_cache><source>Davies 1851</source></_source_cache>
  </resource>
 </entries>
</response>"""


def run_tests(live: bool = False) -> None:
    print("Running pollex_full_import unit tests...")
    failures = 0

    def check(condition: bool, label: str) -> None:
        nonlocal failures
        if condition:
            print(f"PASS: {label}")
        else:
            print(f"FAIL: {label}")
            failures += 1

    # Test 1: Basic parse — one protoform with two clean reflexes
    proto = parse_entry_xml(FIXTURE_BASIC)
    check(proto is not None, "Basic: parse succeeds")
    if proto:
        check(proto["protoform"] == "KAU.2B", "Basic: protoform name")
        check(proto["level"] == "PN", "Basic: level")
        check(proto["slug"] == "kau.2b", "Basic: slug")
        check(proto["description"] == "Group of people, company", "Basic: description")
        check(len(proto["reflexes"]) == 2, "Basic: two reflex rows")
        r0 = proto["reflexes"][0]
        check(r0["language"] == "New Zealand Maori", "Basic: language from _language_cache")
        check(r0["language_code"] == "NZM", "Basic: language code")
        check(r0["item"] == "Kau", "Basic: reflex item")
        check(r0["description"] == "Multitude, company", "Basic: reflex description")
        check(r0["borrowed"] is False, "Basic: borrowed=False")
        check(r0["flag"] == "", "Basic: empty flag")
        check(r0["source"] == "Biggs 1990", "Basic: source citation")
        r1 = proto["reflexes"][1]
        check(r1["flag"] == "", "Basic: 'None' flag normalised to empty")

    # Test 2: Empty entries element
    proto2 = parse_entry_xml(FIXTURE_EMPTY_ENTRIES)
    check(proto2 is not None, "Empty entries: parse succeeds")
    check(proto2 is not None and proto2["reflexes"] == [], "Empty entries: no reflexes")

    # Test 3: No protoform element -> return None
    proto3 = parse_entry_xml(FIXTURE_NO_PROTOFORM)
    check(proto3 is None, "No protoform: returns None")

    # Test 4: Borrowed row
    proto4 = parse_entry_xml(FIXTURE_BORROWED)
    check(proto4 is not None, "Borrowed: parse succeeds")
    if proto4 and proto4["reflexes"]:
        r = proto4["reflexes"][0]
        check(r["borrowed"] is True, "Borrowed: borrowed=True")
        check(r["flag"] == "", "Borrowed: flag empty")

    # Test 5: Flagged rows — P and I flags
    proto5 = parse_entry_xml(FIXTURE_FLAGGED)
    check(proto5 is not None, "Flagged: parse succeeds")
    if proto5:
        flags_seen = [r["flag"] for r in proto5["reflexes"]]
        check("" in flags_seen, "Flagged: clean entry present")
        check("P" in flags_seen, "Flagged: P flag detected")
        check("I" in flags_seen, "Flagged: I flag detected")

    # Test 6: Snapshot -> Register integration via load_from_snapshot
    snapshot = {
        "meta": {"total_protoforms": 1, "total_reflex_rows": 2},
        "protoforms": [parse_entry_xml(FIXTURE_BASIC)],
    }
    import sys as _sys
    sys.path.insert(0, str(ROOT / "tools"))
    from pollex_synonym_register import Register, load_from_snapshot as _lfs
    import json as _json, tempfile as _tf, os as _os
    with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as _tmp:
        _json.dump(snapshot, _tmp, ensure_ascii=False)
        _tmp_path = Path(_tmp.name)
    try:
        reg = Register()
        n = _lfs(_tmp_path, reg)
        check(n == 2, "Snapshot->Register: 2 rows loaded")
        entry = reg.lookup("multitude")
        check(entry is not None and "Kau" in entry["equivalents"], "Snapshot->Register: Multitude -> Kau")
    finally:
        _os.unlink(_tmp_path)

    # Test 7: Borrowed flag propagates through register
    snapshot2 = {
        "meta": {},
        "protoforms": [parse_entry_xml(FIXTURE_BORROWED)],
    }
    with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as _tmp2:
        _json.dump(snapshot2, _tmp2, ensure_ascii=False)
        _tmp2_path = Path(_tmp2.name)
    try:
        reg2 = Register()
        _lfs(_tmp2_path, reg2)
        src = next(iter(reg2.sources.values()), {})
        check("borrowed" in src.get("flags", []), "Borrowed flag propagates to register source")
    finally:
        _os.unlink(_tmp2_path)

    # Test 8: P/I flags propagate through register
    snapshot3 = {
        "meta": {},
        "protoforms": [parse_entry_xml(FIXTURE_FLAGGED)],
    }
    with _tf.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as _tmp3:
        _json.dump(snapshot3, _tmp3, ensure_ascii=False)
        _tmp3_path = Path(_tmp3.name)
    try:
        reg3 = Register()
        _lfs(_tmp3_path, reg3)
        flag_values = [set(s.get("flags", [])) for s in reg3.sources.values()]
        check(any("problematic" in f for f in flag_values), "P flag -> problematic in source")
        check(any("phonologically_irregular" in f for f in flag_values), "I flag -> phonologically_irregular in source")
    finally:
        _os.unlink(_tmp3_path)

    # Test 9: Live network dry-run (optional)
    if live:
        print("\nLive integration test: fetching kau.2b...")
        try:
            import tempfile, os
            td = Path(tempfile.mkdtemp())
            raw = fetch_xml_for_slug("kau.2b", td, delay=0.0)
            check(raw is not None and "<protoform>" in raw, "Live: kau.2b XML fetched")
            proto_live = parse_entry_xml(raw) if raw else None
            check(proto_live is not None, "Live: kau.2b parsed")
            if proto_live:
                check(proto_live["protoform"] == "KAU.2B", "Live: protoform matches")
                check(len(proto_live["reflexes"]) > 0, "Live: has reflexes")
            import shutil
            shutil.rmtree(td, ignore_errors=True)
        except Exception as exc:
            print(f"SKIP: Live test network error: {exc}")

    print()
    if failures == 0:
        print("All tests passed.")
    else:
        print(f"{failures} test(s) FAILED.")
        sys.exit(1)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Full POLLEX snapshot harvester for the synonym register."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    h = sub.add_parser(
        "harvest",
        help="Crawl POLLEX and build pollex-full-snapshot.json.",
    )
    h.add_argument(
        "--out",
        metavar="PATH",
        help=f"Output snapshot path (default: {DEFAULT_SNAPSHOT})",
    )
    h.add_argument(
        "--cache-dir",
        metavar="PATH",
        help=f"XML cache directory (default: {CACHE_DIR})",
    )
    h.add_argument(
        "--delay",
        type=float,
        default=0.15,
        help="Seconds between uncached HTTP requests (default: 0.15)",
    )
    h.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Stop after N slugs (for testing)",
    )
    h.add_argument(
        "--refresh-slugs",
        action="store_true",
        help="Re-crawl the reconstruction index even if slugs.json exists",
    )

    t = sub.add_parser("test", help="Run unit tests.")
    t.add_argument(
        "--live",
        action="store_true",
        help="Include a live network test against kau.2b",
    )

    args = parser.parse_args()

    if args.command == "harvest":
        out = Path(args.out) if args.out else DEFAULT_SNAPSHOT
        cache_dir = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
        harvest(
            out=out,
            cache_dir=cache_dir,
            delay=args.delay,
            limit=args.limit,
            refresh_slugs=args.refresh_slugs,
        )
    elif args.command == "test":
        run_tests(live=args.live)


if __name__ == "__main__":
    main()
