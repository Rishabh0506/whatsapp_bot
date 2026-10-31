"""Unit tests for the diagnosis core (no network, no API key)."""
import asyncio
import io
import json

from PIL import Image

from app.core.pipeline import DiagnosisService
from app.core.prompt import build_schema, load_prompt, to_openapi_schema
from app.core.providers.gemini import GeminiProvider
from app.core.providers.mock import MockProvider
from app.core.rules import apply_rules
from app.core.validation import normalize


def answer(**over):
    base = {
        "visible_evidence": "Brown leather formal shoe, sole lifting at the toe.",
        "image_status": {"value": "Usable", "confidence": 0.95},
        "footwear_type": {"value": "Formal Shoes", "confidence": 0.9},
        "part": {"value": "Sole", "confidence": 0.92},
        "issue_category": {"value": "Breakage / Crack / Gaps", "confidence": 0.9},
        "damage_mode": {"value": "Sole Separation - Partial", "confidence": 0.88},
        "secondary_issue": {"issue_category": "None", "damage_mode": "None", "confidence": 0.8},
        "receiving_substrate": {"value": "Leather", "confidence": 0.85},
        "applied_substrate": {"value": "Rubber", "confidence": 0.82},
        "damage_extent": {"value": "Small / Localised", "confidence": 0.81},
        "glue_fix_possible": {"value": "Yes", "confidence": 0.9},
        "observation_note": "",
    }
    base.update(over)
    return base


def jpeg(color=(120, 80, 40), size=(2400, 1800)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


def test_fields_and_schema(reference):
    assert [f.key for f in reference.fields] == [
        "image_status", "footwear_type", "part", "issue_category", "damage_mode", "secondary_issue",
        "receiving_substrate", "applied_substrate", "damage_extent", "glue_fix_possible"]
    by = reference.by_key
    assert "NA" not in by["receiving_substrate"].values and "NA" in by["applied_substrate"].values
    assert "Unknown" not in by["image_status"].values
    schema = build_schema(reference.fields)
    assert list(schema["properties"])[0] == "visible_evidence"
    assert schema["properties"]["damage_mode"]["properties"]["value"]["enum"] == by["damage_mode"].values
    oa = to_openapi_schema(schema)
    assert oa["type"] == "OBJECT" and oa["propertyOrdering"][1] == "image_status"
    assert oa["properties"]["part"]["properties"]["value"]["type"] == "STRING"


def test_prompt_renders(config_dir, reference):
    text, version = load_prompt(config_dir, "diagnosis_v1", reference)
    assert version == "diagnosis_v1" and "{{" not in text
    assert "Sole Separation - Partial  [Breakage / Crack / Gaps]" in text
    assert "EVA: Ethylene-Vinyl Acetate" in text


def test_all_accepted(reference):
    fields, warnings, extras = normalize(answer(), reference)
    decision = apply_rules(fields, reference, 0.8, 0.5)
    assert warnings == [] and decision["action"] == "accept"
    assert all(f["status"] == "accepted" for f in fields.values())


def test_bands_and_follow_up(reference):
    fields, _, _ = normalize(answer(receiving_substrate={"value": "Leather", "confidence": 0.62},
                                    applied_substrate={"value": "Rubber", "confidence": 0.3},
                                    footwear_type={"value": "Formal Shoes", "confidence": 0.4}), reference)
    d = apply_rules(fields, reference, 0.8, 0.5)
    assert fields["receiving_substrate"]["status"] == "check"
    assert fields["applied_substrate"]["value"] == "Unknown" and fields["applied_substrate"]["model_value"] == "Rubber"
    assert fields["footwear_type"]["value"] == "Unknown"
    # Footwear Type never blocks; the two substrates do
    assert d["action"] == "follow_up" and d["fields"] == ["receiving_substrate", "applied_substrate"]


def test_image_status_decisions(reference):
    f, _, _ = normalize(answer(image_status={"value": "Blurry", "confidence": 0.9}), reference)
    assert apply_rules(f, reference, 0.8, 0.5)["action"] == "better_photo"
    f, _, _ = normalize(answer(image_status={"value": "Damage Not Visible", "confidence": 0.9}), reference)
    assert apply_rules(f, reference, 0.8, 0.5)["action"] == "ask_problem"


def test_validation_catches_problems(reference):
    fields, warnings, _ = normalize(answer(
        part={"value": "Shoelace thing", "confidence": 0.9},          # not in list
        damage_mode={"value": "Water Marks", "confidence": 0.9},      # wrong category for Breakage
        receiving_substrate={"value": "Unknown", "confidence": 0.9},  # unknown material, no note
        glue_fix_possible={"value": "Yes", "confidence": 1.7},        # bad confidence
    ), reference)
    codes = {w["code"] for w in warnings}
    assert fields["part"]["value"] == "Unknown"
    assert fields["glue_fix_possible"]["confidence"] == 1.0
    assert {"not_in_list", "mode_category_mismatch", "unknown_material_no_note", "bad_confidence"} <= codes


def test_universe_checks(reference):
    _, w, _ = normalize(answer(part={"value": "Heel", "confidence": 0.9}), reference)
    assert any(x["code"] == "not_in_universe" for x in w)
    _, w, _ = normalize(answer(footwear_type={"value": "Boots", "confidence": 0.9}), reference)
    assert any(x["code"] == "not_in_universe_for_type" for x in w)
    f, w, _ = normalize(answer(secondary_issue={"issue_category": "Stains / Marks", "damage_mode": "Water Marks",
                                                "confidence": 0.7}), reference)
    assert f["secondary_issue"]["value"] == "Stains / Marks — Water Marks" and w == []


def test_pipeline_with_mock(settings, reference):
    service = DiagnosisService(settings, reference, MockProvider(reference))
    r1 = asyncio.run(service.diagnose([jpeg(), jpeg((10, 10, 10))]))
    r2 = asyncio.run(service.diagnose([jpeg(), jpeg((10, 10, 10))]))
    assert r1["fields"] == r2["fields"]                      # mock is repeatable
    assert r1["meta"]["image_count"] == 2 and len(r1["order"]) == 10
    assert r1["decision"]["action"] in ("accept", "follow_up", "better_photo", "ask_problem")


def test_gemini_request_and_parse(reference):
    g = GeminiProvider("k", "gemini-x", "https://example", temperature=0.2,
                       generation_config_extra={"thinkingConfig": {"thinkingLevel": "low"}})
    from app.core.providers.base import ImageInput
    schema = build_schema(reference.fields)
    body = g.build_request([ImageInput(b"abc")], "do it", schema, "json_schema")
    gen = body["generationConfig"]
    assert gen["responseMimeType"] == "application/json" and gen["responseJsonSchema"] == schema
    assert gen["temperature"] == 0.2 and gen["thinkingConfig"] == {"thinkingLevel": "low"}
    assert body["contents"][0]["parts"][0]["inlineData"]["data"] == "YWJj"
    body2 = g.build_request([ImageInput(b"abc")], "do it", schema, "openapi")
    assert "responseSchema" in body2["generationConfig"]
    resp = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                  {"text": json.dumps(answer())}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200, "totalTokenCount": 1300},
            "modelVersion": "gemini-x-001"}
    text, out = GeminiProvider.parse_response(resp)
    assert out["parsed"]["part"]["value"] == "Sole" and out["usage"]["input_tokens"] == 1000
