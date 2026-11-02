"""What the customer reads in the chat. Plain language only: no field names, scores or decision codes.
The full diagnosis (fields, confidences, decision) is on the backend dashboard, never in the chat.

Edit the wording here freely. The solution/product step will extend `diagnosis()` later."""
from __future__ import annotations

UNKNOWN_VALUES = {"Unknown", "None", "NA", None}

# How each footwear type is named in a sentence ("your ___").
FOOTWEAR = {
    "Formal Shoes": "formal shoes",
    "Casual Shoes": "casual shoes",
    "Sports Shoes": "sports shoes",
    "Clogs": "clogs",
    "Slippers": "slippers",
    "Sandals": "sandals",
    "High Heels": "heels",
    "Boots": "boots",
    "Ethnic Footwear": "footwear",
}

# Each damage mode in everyday words. Anything missing here falls back to the damage mode in lower case.
DAMAGE = {
    "Sole Separation - Partial": "the sole is coming off in one area",
    "Sole Separation - Full": "the sole has come off completely",
    "Sole Cracked / Broken Through": "the sole is cracked or broken through",
    "Heel Detached": "the heel has come off",
    "Heel Broken / Snapped": "the heel is broken",
    "Heel Tip Lost / Broken": "the heel tip is broken or missing",
    "Strap Detached / Pulled Out": "a strap has come loose",
    "Strap Snapped / Broken": "a strap has broken",
    "Closure Broken (Velcro / Buckle / Zip)": "the closure (velcro, buckle or zip) is broken",
    "Embellishment Detached": "a decoration has come off",
    "Lace Snapped": "a lace has snapped",
    "Aglet Frayed / Lost": "the tip of a lace is frayed or missing",
    "Hole / Tear in Upper": "there is a hole or tear in the upper",
    "Seam Opened": "a seam has opened",
    "Lining Torn": "the inner lining is torn",
    "Lace Frayed / Torn": "a lace is frayed or torn",
    "Footbed Cover Lifted / Torn": "the insole cover is lifting or torn",
    "Peeling (PU / Covering)": "the outer layer is peeling",
    "Scuff Marks": "there are scuff marks",
    "Scratches": "there are scratches",
    "Dirt / Grime": "it has dirt and grime on it",
    "Water Marks": "there are water marks",
    "Food Stain": "there is a food stain",
    "Paint Stain": "there is a paint stain",
    "Oil / Grease Stain": "there is an oil or grease stain",
    "Stain - Type Not Specified": "there is a stain",
    "Preventive Care": "they could do with some care to keep them in good shape",
    "Colour Faded": "the colour has faded",
    "Shine / Polish Lost": "they have lost their shine",
    "Worn Out": "they are worn out",
    "Loss of Grip": "the sole has lost its grip",
    "Loss of Shape": "they have lost their shape",
    "Creases": "there are creases",
    "Foot Odour": "they have an odour",
    "Musty / Damp Smell": "they have a musty, damp smell",
    "Squeaking": "they squeak",
}

# What we can say about a glue repair.
GLUE = {
    "Yes": "Good news: this can be fixed at home with the right adhesive.",
    "No – Weight-Bearing Part": "This part carries your weight, so glue alone won't hold it safely. "
                                "It's best taken to a cobbler.",
    "No – Material Destroyed": "The material itself is damaged, so glue won't fix this. "
                               "A cobbler can tell you whether it can be repaired.",
    "No – Surface Glue Cannot Hold": "These surfaces won't hold glue well, so a glue repair isn't recommended. "
                                     "A cobbler is the safer option.",
    "No – Not a Glue Problem": "This isn't something glue fixes; it needs cleaning or care instead.",
}

BETTER_PHOTO = {
    "Blurry": "The photo is a bit too blurry or dark for me to see the problem clearly. "
              "Could you send another one in good light, holding the phone steady?",
    "Not Footwear": "I couldn't find any footwear in that photo. "
                    "Please send a photo of the shoe or sandal that needs fixing.",
    "More Than One Item": "I can see more than one item in the photo. "
                          "Please send a photo of just the one that needs fixing.",
}

CLOSER_PHOTO = "Could you send one more photo, close up on the damaged area? A second angle helps too."


def _known(fields: dict, key: str) -> str | None:
    """The field's value if it was accepted, else None (we only tell the customer what we're sure about)."""
    f = fields.get(key) or {}
    if f.get("status") != "accepted" or f.get("value") in UNKNOWN_VALUES:
        return None
    return f["value"]


def _damage(fields: dict) -> tuple[str, str | None]:
    """(how to name the footwear, the damage in everyday words or None if not sure)."""
    footwear = FOOTWEAR.get(_known(fields, "footwear_type") or "", "footwear")
    mode = _known(fields, "damage_mode")
    return footwear, (DAMAGE.get(mode, mode.lower()) if mode else None)


def _secondary_sentence(fields: dict) -> str | None:
    sec = fields.get("secondary_issue") or {}
    mode = sec.get("damage_mode")
    if sec.get("status") != "accepted" or mode in UNKNOWN_VALUES:
        return None
    return f"I also noticed that {DAMAGE.get(mode, mode.lower())}."


def diagnosis(result: dict, diagnosis_id: int | None = None) -> str:
    fields, action = result["fields"], result["decision"]["action"]

    if action == "better_photo":
        status = (fields.get("image_status") or {}).get("value")
        return BETTER_PHOTO.get(status, "I couldn't see the problem clearly. Could you send a clearer photo?")

    if action == "ask_problem":
        return ("Thanks for the photo! I couldn't spot any damage in it. "
                "Could you send a close-up photo of the part that has the problem?")

    footwear, what = _damage(fields)
    if action == "follow_up":
        # not sure enough about something that decides the fix -> ask for a better look
        seen = f"It looks like {what}, but I want to be sure before suggesting a fix." if what \
            else f"I want to be sure what's wrong with your {footwear} before suggesting a fix."
        return "\n\n".join(["Thanks for the photo!", seen, CLOSER_PHOTO])

    # accept: every field that decides the fix is confident
    seen = f"Here's what I can see on your {footwear}: {what}." if what else f"I've had a good look at your {footwear}."
    secondary = _secondary_sentence(fields)
    lines = ["Thanks for the photo!", seen + (" " + secondary if secondary else "")]
    glue = GLUE.get(_known(fields, "glue_fix_possible") or "")
    if glue:
        lines.append(glue)
    return "\n\n".join(lines)


def error(exc: Exception) -> str:
    # the technical error is stored with the diagnosis and shown on the dashboard, not to the customer
    return "Sorry, something went wrong on our side while looking at your photo. Please try sending it again."


def text_not_supported() -> str:
    return "Hi! 👋 Please send a photo of the footwear that needs fixing and I'll take a look."


def type_not_supported(kind: str) -> str:
    return "Sorry, I can't open that kind of message yet. Please send a photo of the footwear that needs fixing."


def media_failed() -> str:
    return "Sorry, I couldn't download that photo. Please send it again."
