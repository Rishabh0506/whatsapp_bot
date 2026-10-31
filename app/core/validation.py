"""Checks the model's answer against the Lists and the Universe. Never trusts the model blindly:
values outside the lists become Unknown, and inconsistencies are recorded as warnings."""
from __future__ import annotations

from .reference import NONE, UNKNOWN, Reference


def _conf(raw) -> tuple[float, bool]:
    try:
        c = float(raw)
    except (TypeError, ValueError):
        return 0.0, False
    ok = 0.0 <= c <= 1.0
    return min(max(c, 0.0), 1.0), ok


def normalize(parsed: dict, ref: Reference) -> tuple[dict, list[dict], dict]:
    """Returns (fields, warnings, extras). fields[key] = {label, value, confidence, model_value, ...}."""
    warnings: list[dict] = []

    def warn(code, field, message):
        warnings.append({"code": code, "field": field, "message": message})

    fields: dict = {}
    for f in ref.fields:
        item = parsed.get(f.key)
        if not isinstance(item, dict):
            warn("missing_field", f.key, f"{f.label} missing from the model's answer")
            item = {}
        conf, ok = _conf(item.get("confidence"))
        if not ok:
            warn("bad_confidence", f.key, f"{f.label}: confidence {item.get('confidence')!r} not in 0-1")
        if f.kind == "issue_pair":
            cat, mode = item.get("issue_category", NONE), item.get("damage_mode", NONE)
            if cat not in f.category_values:
                warn("not_in_list", f.key, f"Secondary issue category '{cat}' is not in the Lists")
                cat = UNKNOWN
            if mode not in f.mode_values:
                warn("not_in_list", f.key, f"Secondary damage mode '{mode}' is not in the Lists")
                mode = UNKNOWN
            if (cat == NONE) != (mode == NONE):
                warn("pair_incomplete", f.key, "Secondary issue has None for only one of category / damage mode")
            value = NONE if cat == NONE and mode == NONE else f"{cat} — {mode}"
            fields[f.key] = {"label": f.label, "value": value, "confidence": conf, "model_value": value,
                             "issue_category": cat, "damage_mode": mode}
            continue
        value = item.get("value")
        if value not in f.values:
            warn("not_in_list", f.key, f"{f.label}: '{value}' is not an allowed value")
            value = UNKNOWN if f.allows_unknown else None
        fields[f.key] = {"label": f.label, "value": value, "confidence": conf, "model_value": value}

    extras = {"visible_evidence": str(parsed.get("visible_evidence") or ""),
              "observation_note": str(parsed.get("observation_note") or "")}
    consistency_checks(fields, ref, extras, warn)
    return fields, warnings, extras


def consistency_checks(fields: dict, ref: Reference, extras: dict, warn) -> None:
    v = lambda k: (fields.get(k) or {}).get("value")  # noqa: E731
    ftype, part, cat, mode = v("footwear_type"), v("part"), v("issue_category"), v("damage_mode")

    if mode and cat and UNKNOWN not in (mode, cat) and ref.mode_category.get(mode) not in (cat, None):
        warn("mode_category_mismatch", "damage_mode",
             f"Damage mode '{mode}' belongs to '{ref.mode_category[mode]}', not '{cat}'")
    if ref.universe and None not in (part, cat, mode) and UNKNOWN not in (part, cat, mode):
        if (part, cat, mode) not in ref.combos:
            warn("not_in_universe", "damage_mode", f"No Universe row has Part '{part}' + '{cat}' + '{mode}'")
        elif ftype and ftype != UNKNOWN and (ftype, part, cat, mode) not in ref.combos_type:
            warn("not_in_universe_for_type", "footwear_type",
                 f"The Universe has this problem, but not for {ftype}")

    sec = fields.get("secondary_issue")
    if sec and sec["value"] not in (NONE,) and UNKNOWN not in (sec["issue_category"], sec["damage_mode"]):
        if ref.universe and (sec["issue_category"], sec["damage_mode"]) not in ref.pairs:
            warn("not_in_universe", "secondary_issue", "Secondary issue pair does not appear in the Universe")
        if (sec["issue_category"], sec["damage_mode"]) == (cat, mode):
            warn("secondary_same_as_main", "secondary_issue", "Secondary issue repeats the main issue")

    for k in ("receiving_substrate", "applied_substrate"):
        f = fields.get(k)
        if f and f["model_value"] == UNKNOWN and not extras["observation_note"].strip():
            warn("unknown_material_no_note", k,
                 f"{f['label']} is Unknown but the observation note does not describe the material")
