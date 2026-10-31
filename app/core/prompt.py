"""Builds the model instructions and the structured-output schema from the field definitions."""
from __future__ import annotations

import copy
from pathlib import Path

from .reference import FieldDef, Reference


def load_prompt(config_dir: Path, name: str, ref: Reference) -> tuple[str, str]:
    """Returns (prompt text, prompt version). The file is read each time, so edits apply at once."""
    raw = (config_dir / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    version = name
    body = raw
    if raw.startswith("---"):
        _, front, body = raw.split("---", 2)
        for line in front.splitlines():
            if line.strip().startswith("version:"):
                version = line.split(":", 1)[1].strip()
    abbreviations = "\n".join(f"- {k}: {v}" for k, v in ref.abbreviations.items()) or "(none)"
    text = body.strip().replace("{{ABBREVIATIONS}}", abbreviations).replace("{{FIELD_SPEC}}", field_spec(ref))
    return text, version


def field_spec(ref: Reference) -> str:
    parts = []
    for i, f in enumerate(ref.fields, 1):
        lines = [f"### {i}. {f.label}  (output key: `{f.key}`)", f.description]
        if f.kind == "issue_pair":
            lines.append("Answer as `issue_category` + `damage_mode`, using the same lists as fields "
                         "Issue Category and Damage Mode, or None for both.")
        elif f.key == "damage_mode":
            lines.append("Allowed values (issue category in brackets):")
            lines += [f"- {v}" + (f"  [{ref.mode_category[v]}]" if v in ref.mode_category and v != "Unknown" else "")
                      for v in f.values]
        else:
            lines.append("Allowed values: " + "; ".join(f.values))
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def _conf(desc: str = "Probability that this value is correct, 0.00-1.00") -> dict:
    return {"type": "number", "minimum": 0, "maximum": 1, "description": desc}


def build_schema(fields: list[FieldDef]) -> dict:
    """JSON Schema for Gemini structured output; enums keep every value inside the allowed lists."""
    props: dict = {"visible_evidence": {"type": "string",
                                        "description": "Short description of what is visible that supports the answer."}}
    for f in fields:
        if f.kind == "issue_pair":
            props[f.key] = {
                "type": "object",
                "properties": {
                    "issue_category": {"type": "string", "enum": f.category_values},
                    "damage_mode": {"type": "string", "enum": f.mode_values},
                    "confidence": _conf(),
                },
                "required": ["issue_category", "damage_mode", "confidence"],
            }
        else:
            props[f.key] = {
                "type": "object",
                "properties": {"value": {"type": "string", "enum": f.values}, "confidence": _conf()},
                "required": ["value", "confidence"],
            }
    props["observation_note"] = {"type": "string",
                                 "description": "Notes for a human reviewer; empty string if none."}
    return {"type": "object", "properties": props, "required": list(props)}


def to_openapi_schema(schema: dict) -> dict:
    """Converts the JSON Schema to Gemini's older OpenAPI-style responseSchema (uppercase types, propertyOrdering)."""
    s = copy.deepcopy(schema)

    def walk(node):
        if isinstance(node, dict):
            if "type" in node and isinstance(node["type"], str):
                node["type"] = node["type"].upper()
            if "properties" in node:
                node["propertyOrdering"] = list(node["properties"])
                for v in node["properties"].values():
                    walk(v)
        return node

    return walk(s)
