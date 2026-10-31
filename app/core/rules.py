"""Confidence bands and the decision (spec section 4). Bands come from settings, so the
final values from the test plan are a settings change, not a code change."""
from __future__ import annotations

from .reference import UNKNOWN, Reference

ACCEPTED, CHECK, LOW = "accepted", "check", "unknown"

# Image Status values that mean "this photo can't be used"
BETTER_PHOTO = {"Blurry", "Not Footwear", "More Than One Item"}


def apply_rules(fields: dict, ref: Reference, accept: float, unknown_below: float) -> dict:
    """Sets each field's status (and Unknown below the lower band). Returns the decision."""
    for f in ref.fields:
        item = fields[f.key]
        conf = item["confidence"]
        if item["value"] in (UNKNOWN, None) or conf < unknown_below:
            item["status"] = LOW
            if conf < unknown_below and f.allows_unknown and item["value"] not in (UNKNOWN, None):
                item["value"] = UNKNOWN          # model's answer kept in model_value
        elif conf < accept:
            item["status"] = CHECK
        else:
            item["status"] = ACCEPTED

    status = fields.get("image_status", {})
    if status.get("value") in BETTER_PHOTO:
        return {"action": "better_photo", "fields": ["image_status"],
                "reason": f"Image Status is {status['value']}"}
    if status.get("value") == "Damage Not Visible":
        # spec section 5: photo shows no damage and there is no text -> ask what the problem is
        return {"action": "ask_problem", "fields": ["image_status"],
                "reason": "No damage visible in the photo"}

    pending = [f.key for f in ref.fields if f.product_deciding and fields[f.key]["status"] != ACCEPTED]
    if pending:
        labels = ", ".join(fields[k]["label"] for k in pending)
        return {"action": "follow_up", "fields": pending,
                "reason": f"Below {accept:.2f} or Unknown on product-deciding field(s): {labels}"}
    return {"action": "accept", "fields": [], "reason": "All product-deciding fields at or above the accept band"}
