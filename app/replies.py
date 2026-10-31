"""What the bot says. For now (test mode) the diagnosis reply lists the 10 fields with their confidence.
The consumer-facing wording (solutions, follow-up questions) replaces this later."""
from __future__ import annotations

ICON = {"accepted": "✅", "check": "⚠️", "unknown": "❓"}
ACTION = {
    "accept": "Accept",
    "follow_up": "Follow-up needed",
    "better_photo": "Ask for a better photo",
    "ask_problem": "Ask what the problem is",
}


def diagnosis(result: dict, diagnosis_id: int) -> str:
    meta, fields = result["meta"], result["fields"]
    n = meta["image_count"]
    lines = [f"🧪 Test mode · diagnosis #{diagnosis_id} ({n} photo{'s' if n != 1 else ''})", ""]
    for i, key in enumerate(result["order"], 1):
        f = fields[key]
        line = f"{i}. {f['label']}: {f['value']} · {f['confidence']:.2f} {ICON.get(f.get('status'), '')}"
        if f["value"] != f["model_value"]:
            line += f" (model said: {f['model_value']})"
        lines.append(line)
    d = result["decision"]
    decision = ACTION.get(d["action"], d["action"])
    if d["action"] == "follow_up":
        decision += " — " + ", ".join(fields[k]["label"] for k in d["fields"])
    b = meta["bands"]
    lines += ["", f"Decision: {decision}",
              f"✅ ≥{b['accept']:.2f}  ⚠️ {b['unknown_below']:.2f}–{b['accept']:.2f}  ❓ <{b['unknown_below']:.2f}"]
    if result["warnings"]:
        lines.append(f"{len(result['warnings'])} check warning(s) — see the debug panel")
    return "\n".join(lines)


def error(exc: Exception) -> str:
    return f"🧪 Test mode · the diagnosis failed: {str(exc)[:300]}"


def text_not_supported() -> str:
    return "🧪 Test mode · for now I can only diagnose photos. Please send a photo of the footwear."


def type_not_supported(kind: str) -> str:
    return f"🧪 Test mode · {kind} messages aren't supported yet. Please send a photo of the footwear."


def media_failed() -> str:
    return "🧪 Test mode · I couldn't download that photo. Please send it again."
