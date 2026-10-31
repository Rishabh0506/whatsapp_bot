"""Reference data (Lists + Universe) and the field definitions built from config/fields.yaml."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

UNKNOWN = "Unknown"
NONE = "None"


@dataclass
class FieldDef:
    key: str
    label: str
    kind: str                      # "single" or "issue_pair"
    values: list[str]              # allowed values ("single" fields)
    product_deciding: bool
    description: str
    category_values: list[str] = field(default_factory=list)   # issue_pair: allowed issue categories
    mode_values: list[str] = field(default_factory=list)       # issue_pair: allowed damage modes

    @property
    def allows_unknown(self) -> bool:
        return self.kind == "issue_pair" or UNKNOWN in self.values


class ReferenceDataError(Exception):
    pass


class Reference:
    def __init__(self, lists: dict, universe_rows: list[dict], fields: list[FieldDef]):
        self.lists = lists
        self.universe = universe_rows
        self.fields = fields
        self.by_key = {f.key: f for f in fields}
        self.mode_category: dict[str, str] = lists.get("damage_mode_category", {})
        self.abbreviations: dict[str, str] = lists.get("abbreviations", {})
        u = universe_rows
        self.combos_type = {(r["footwear_type"], r["part"], r["issue_category"], r["damage_mode"]) for r in u}
        self.combos = {(r["part"], r["issue_category"], r["damage_mode"]) for r in u}
        self.pairs = {(r["issue_category"], r["damage_mode"]) for r in u}

    @classmethod
    def load(cls, config_dir: Path) -> "Reference":
        ref = config_dir / "reference"
        lists_p, uni_p = ref / "lists.json", ref / "universe.json"
        if not lists_p.exists() or not uni_p.exists():
            raise ReferenceDataError(
                "Reference data missing. Put Shoe_Fixing_Lists.xlsx and Shoe_Fixing_Universe.xlsx in "
                "config/reference/ and run:  python scripts/import_reference.py")
        lists = json.loads(lists_p.read_text(encoding="utf-8"))
        universe = json.loads(uni_p.read_text(encoding="utf-8"))["rows"]
        spec = yaml.safe_load((config_dir / "fields.yaml").read_text(encoding="utf-8"))["fields"]
        return cls(lists, universe, build_fields(spec, lists))

    def source_info(self) -> dict:
        return {"lists": self.lists.get("_source", {}), "universe_rows": len(self.universe)}


def build_fields(spec: list[dict], lists: dict) -> list[FieldDef]:
    out = []
    for f in spec:
        kind = f.get("kind", "single")
        desc = " ".join(str(f.get("description", "")).split())
        if kind == "issue_pair":
            cats = [v for v in lists["issue_category"] if v != UNKNOWN] + [UNKNOWN, NONE]
            modes = [v for v in lists["damage_mode"] if v != UNKNOWN] + [UNKNOWN, NONE]
            out.append(FieldDef(f["key"], f["label"], kind, [], bool(f.get("product_deciding")), desc,
                                category_values=cats, mode_values=modes))
            continue
        if "values" in f:
            values = [str(v) for v in f["values"]]
        else:
            if f["list"] not in lists:
                raise ReferenceDataError(f"fields.yaml: field '{f['key']}' uses list '{f['list']}' which is not in lists.json")
            values = list(lists[f["list"]])
        exclude = set(f.get("exclude", []))
        values = [v for v in values if v not in exclude]
        out.append(FieldDef(f["key"], f["label"], kind, values, bool(f.get("product_deciding")), desc))
    return out
