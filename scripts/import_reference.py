"""Import the Shoe Fixing workbooks into the bot's reference files.

Reads   config/reference/Shoe_Fixing_Lists.xlsx     (sheet "Lists")
        config/reference/Shoe_Fixing_Universe.xlsx  (sheet "Footwear")
Writes  config/reference/lists.json
        config/reference/universe.json

Run it again whenever you edit the workbooks:
    python scripts/import_reference.py
Only needs openpyxl.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import openpyxl

REF = Path(__file__).resolve().parent.parent / "config" / "reference"
LISTS_XLSX = REF / "Shoe_Fixing_Lists.xlsx"
UNIVERSE_XLSX = REF / "Shoe_Fixing_Universe.xlsx"


def clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def is_total(s):
    return s is None or s.lower().startswith("total")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read_lists(path: Path) -> dict:
    ws = openpyxl.load_workbook(path, data_only=True)["Lists"]
    rows = [[clean(c) for c in r] for r in ws.iter_rows(values_only=True)]
    # header row = the one containing "Part"
    h = next(i for i, r in enumerate(rows) if "Part" in r)
    head = rows[h]
    col = {name: head.index(name) for name in head if name}
    body = rows[h + 1:]

    def column(c):
        out = []
        for r in body:
            v = r[c] if c < len(r) else None
            if is_total(v):
                if v is not None:
                    break
                continue
            if v not in out:
                out.append(v)
        return out

    # Footwear Type has no header: it is the column right after the SN column (column B)
    footwear = column(1)
    part = column(col["Part"])
    issue_unique = column(col["Issue Category (unique)"])
    substrate = column(col["Substrate"])

    damage_mode, mode_category = [], {}
    ci, cm = col["Issue Category"], col["Damage Mode"]
    for r in body:
        cat, mode = r[ci], r[cm]
        if cat is None or mode is None or is_total(cat):
            continue
        if mode not in damage_mode:
            damage_mode.append(mode)
            mode_category[mode] = cat

    abbreviations = {}
    ca, cf = col.get("Abbreviation"), col.get("Full Form")
    if ca is not None and cf is not None:
        for r in body:
            a, f = r[ca], r[cf]
            if a and f and a not in ("SN",) and not is_total(a):
                abbreviations[a] = f

    return {
        "footwear_type": footwear,
        "part": part,
        "issue_category": issue_unique,
        "damage_mode": damage_mode,
        "damage_mode_category": mode_category,
        "substrate": substrate,
        "abbreviations": abbreviations,
    }


UNIVERSE_COLS = {
    "Object": "object",
    "Footwear Type": "footwear_type",
    "Part": "part",
    "Issue Category": "issue_category",
    "Damage Mode": "damage_mode",
    "User Fixing Queries": "user_query",
    "Receiving Substrate": "receiving_substrate",
    "Applied Substrate": "applied_substrate",
}


def read_universe(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Footwear"] if "Footwear" in wb.sheetnames else wb.worksheets[0]
    rows = [[clean(c) for c in r] for r in ws.iter_rows(values_only=True)]
    head = rows[0]
    idx = {}
    for i, name in enumerate(head):
        if not name:
            continue
        for prefix, key in UNIVERSE_COLS.items():
            if name.startswith(prefix) and key not in idx:
                idx[key] = i
    out = []
    for r in rows[1:]:
        if not any(r):
            continue
        item = {"sn": len(out) + 1}
        for key, i in idx.items():
            item[key] = r[i] if i < len(r) else None
        out.append(item)
    return out


def check(lists: dict, universe: list[dict]) -> list[str]:
    problems = []
    subs = set(lists["substrate"])
    for u in universe:
        for key in ("footwear_type", "part", "issue_category", "damage_mode"):
            if u.get(key) not in lists[key]:
                problems.append(f"Universe row {u['sn']}: {key} '{u.get(key)}' is not in the Lists sheet")
        for key in ("receiving_substrate", "applied_substrate"):
            cell = u.get(key) or ""
            rest = cell
            for s in sorted(subs, key=len, reverse=True):   # multi-word values contain '/'
                rest = rest.replace(s, "")
            if rest.replace("/", "").strip():
                problems.append(f"Universe row {u['sn']}: {key} '{cell}' has a value not in the Substrate list")
        if lists["damage_mode_category"].get(u.get("damage_mode")) not in (u.get("issue_category"), None):
            problems.append(f"Universe row {u['sn']}: damage mode '{u['damage_mode']}' belongs to a different issue category in Lists")
    return problems


def main():
    for p in (LISTS_XLSX, UNIVERSE_XLSX):
        if not p.exists():
            sys.exit(f"Missing {p}. Copy the workbook into config/reference/ first.")
    lists = read_lists(LISTS_XLSX)
    universe = read_universe(UNIVERSE_XLSX)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lists["_source"] = {"file": LISTS_XLSX.name, "sha256": sha256(LISTS_XLSX), "imported_at": stamp}
    (REF / "lists.json").write_text(json.dumps(lists, indent=2, ensure_ascii=False), encoding="utf-8")
    (REF / "universe.json").write_text(json.dumps(
        {"_source": {"file": UNIVERSE_XLSX.name, "sha256": sha256(UNIVERSE_XLSX), "imported_at": stamp},
         "rows": universe}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Imported:")
    for k in ("footwear_type", "part", "issue_category", "damage_mode", "substrate"):
        print(f"  {k:15s} {len(lists[k]):3d} values")
    print(f"  universe        {len(universe):3d} rows")
    problems = check(lists, universe)
    print("Checks:", "all values match" if not problems else f"{len(problems)} problem(s)")
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    main()
