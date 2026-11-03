"""What the customer reads in the chat, in English (en) and Hindi (hi, in Hindi letters).
Plain language only: no field names, scores or decision codes. The full diagnosis (fields, confidences,
decision) is on the backend dashboard, never in the chat.

Edit the wording here freely; every message has an English and a Hindi version. The Hindi wording should be
checked by a Hindi speaker before going live. When the language is not chosen yet (lang=None), messages are
sent in both languages. The product / step-by-step part will replace SOLUTION_PLACEHOLDER later."""
from __future__ import annotations

UNKNOWN_VALUES = {"Unknown", "None", "NA", None}


def _both(en: str, hi: str) -> str:
    return f"{en}\n\n{hi}"


def _pick(lang: str | None, en: str, hi: str) -> str:
    if lang == "hi":
        return hi
    if lang == "en":
        return en
    return _both(en, hi)


# ---------------------------------------------------------------- footwear and damage in everyday words
# English: how each footwear type is named in a sentence ("your ___").
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
# Hindi: "your ___" already in the form used before में / को ("आपके फ़ॉर्मल जूतों में").
FOOTWEAR_HI = {
    "Formal Shoes": "आपके फ़ॉर्मल जूतों",
    "Casual Shoes": "आपके कैज़ुअल जूतों",
    "Sports Shoes": "आपके स्पोर्ट्स शूज़",
    "Clogs": "आपके क्लॉग्स",
    "Slippers": "आपकी चप्पल",
    "Sandals": "आपकी सैंडल",
    "High Heels": "आपकी हील वाली सैंडल",
    "Boots": "आपके बूट",
    "Ethnic Footwear": "आपकी जूती",
}
FOOTWEAR_DEFAULT = {"en": "footwear", "hi": "आपके जूते-चप्पल"}

# Each damage mode in everyday words. Anything missing falls back to the damage mode in lower case (English)
# or a general phrase (Hindi).
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
DAMAGE_HI = {
    "Sole Separation - Partial": "सोल एक जगह से उखड़ रहा है",
    "Sole Separation - Full": "सोल पूरी तरह से निकल गया है",
    "Sole Cracked / Broken Through": "सोल में दरार है या वह टूट गया है",
    "Heel Detached": "हील निकल गई है",
    "Heel Broken / Snapped": "हील टूट गई है",
    "Heel Tip Lost / Broken": "हील का निचला सिरा (टिप) टूट गया है या गायब है",
    "Strap Detached / Pulled Out": "एक स्ट्रैप ढीला होकर निकल गया है",
    "Strap Snapped / Broken": "एक स्ट्रैप टूट गया है",
    "Closure Broken (Velcro / Buckle / Zip)": "बंद करने वाला हिस्सा (वेल्क्रो, बकल या ज़िप) टूट गया है",
    "Embellishment Detached": "सजावट का कोई हिस्सा निकल गया है",
    "Lace Snapped": "फीता टूट गया है",
    "Aglet Frayed / Lost": "फीते का सिरा उधड़ गया है या गायब है",
    "Hole / Tear in Upper": "ऊपरी हिस्से में छेद है या वह फट गया है",
    "Seam Opened": "सिलाई खुल गई है",
    "Lining Torn": "अंदर की लाइनिंग फट गई है",
    "Lace Frayed / Torn": "फीता घिस गया है या फट गया है",
    "Footbed Cover Lifted / Torn": "अंदर के तले (इनसोल) का कवर उठ गया है या फट गया है",
    "Peeling (PU / Covering)": "ऊपर की परत उखड़ रही है",
    "Scuff Marks": "रगड़ के निशान हैं",
    "Scratches": "खरोंचें हैं",
    "Dirt / Grime": "धूल-मिट्टी और गंदगी जमी है",
    "Water Marks": "पानी के दाग हैं",
    "Food Stain": "खाने का दाग है",
    "Paint Stain": "पेंट का दाग है",
    "Oil / Grease Stain": "तेल या ग्रीस का दाग है",
    "Stain - Type Not Specified": "एक दाग है",
    "Preventive Care": "इन्हें अच्छी हालत में रखने के लिए थोड़ी देखभाल की ज़रूरत है",
    "Colour Faded": "रंग फीका पड़ गया है",
    "Shine / Polish Lost": "चमक चली गई है",
    "Worn Out": "ये घिस गए हैं",
    "Loss of Grip": "सोल की पकड़ (ग्रिप) कम हो गई है",
    "Loss of Shape": "इनका आकार बिगड़ गया है",
    "Creases": "सिलवटें पड़ गई हैं",
    "Foot Odour": "इनमें से बदबू आ रही है",
    "Musty / Damp Smell": "इनमें से सीलन जैसी बदबू आ रही है",
    "Squeaking": "चलते समय इनमें से चूँ-चूँ की आवाज़ आती है",
}

# What we can say about a glue repair. The three "No" reasons that send the customer to a cobbler are a
# placeholder for the cobbler rules still to come (see app/core/rules.py).
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
GLUE_HI = {
    "Yes": "अच्छी खबर: सही एडहेसिव (गोंद) से इसे घर पर ठीक किया जा सकता है।",
    "No – Weight-Bearing Part": "इस हिस्से पर आपके शरीर का वज़न पड़ता है, इसलिए सिर्फ़ गोंद से यह सुरक्षित रूप से "
                                "नहीं टिकेगा। इसे मोची के पास ले जाना बेहतर रहेगा।",
    "No – Material Destroyed": "सामग्री ही खराब हो चुकी है, इसलिए गोंद से यह ठीक नहीं होगा। "
                               "मोची बता पाएँगे कि इसकी मरम्मत हो सकती है या नहीं।",
    "No – Surface Glue Cannot Hold": "ये सतहें गोंद को ठीक से नहीं पकड़तीं, इसलिए गोंद से मरम्मत की सलाह नहीं दी "
                                     "जाती। मोची के पास ले जाना ज़्यादा सुरक्षित रहेगा।",
    "No – Not a Glue Problem": "यह गोंद से ठीक होने वाली समस्या नहीं है; इसके लिए सफ़ाई या देखभाल की ज़रूरत है।",
}

# Until the product / step-by-step rules arrive, a confident answer ends with this line.
SOLUTION_PLACEHOLDER = {
    "en": "[Product recommendation and step-by-step guidance will be added here.]",
    "hi": "[यहाँ प्रोडक्ट की सलाह और स्टेप-बाय-स्टेप तरीका जोड़ा जाएगा।]",
}

BETTER_PHOTO = {
    "Blurry": ("The photo is a bit too blurry or dark for me to see the problem clearly. "
               "Could you send another one in good light, holding the phone steady?",
               "फ़ोटो थोड़ी धुंधली या अंधेरी है, इसलिए समस्या साफ़ नहीं दिख रही। क्या आप अच्छी रोशनी में, फ़ोन "
               "स्थिर रखकर एक और फ़ोटो भेज सकते हैं?"),
    "Not Footwear": ("I couldn't find any footwear in that photo. "
                     "Please send a photo of the shoe or sandal that needs fixing.",
                     "इस फ़ोटो में हमें कोई जूता या चप्पल नहीं दिखा। कृपया उस जूते या चप्पल की फ़ोटो भेजें जिसे "
                     "ठीक करना है।"),
    "More Than One Item": ("I can see more than one item in the photo. "
                           "Please send a photo of just the one that needs fixing.",
                           "फ़ोटो में एक से ज़्यादा चीज़ें दिख रही हैं। कृपया सिर्फ़ उसी की फ़ोटो भेजें जिसे ठीक "
                           "करना है।"),
}
BETTER_PHOTO_DEFAULT = ("I couldn't see the problem clearly. Could you send a clearer photo?",
                        "हमें समस्या साफ़ नहीं दिखी। क्या आप एक साफ़ फ़ोटो भेज सकते हैं?")

CLOSER_PHOTO = ("Could you send one more photo, close up on the damaged area? A second angle helps too.",
                "क्या आप खराब हिस्से की पास से एक और फ़ोटो भेज सकते हैं? किसी दूसरे एंगल से फ़ोटो हो तो और भी "
                "मदद मिलेगी।")


# ---------------------------------------------------------------- helpers on the diagnosis result
def _known(fields: dict, key: str) -> str | None:
    """The field's value if it was accepted, else None (we only tell the customer what we're sure about)."""
    f = fields.get(key) or {}
    if f.get("status") != "accepted" or f.get("value") in UNKNOWN_VALUES:
        return None
    return f["value"]


def _damage(fields: dict, lang: str) -> tuple[str, str | None]:
    """(how to name the footwear, the damage in everyday words or None if not sure)."""
    ft, mode = _known(fields, "footwear_type"), _known(fields, "damage_mode")
    if lang == "hi":
        return FOOTWEAR_HI.get(ft or "", FOOTWEAR_DEFAULT["hi"]), (DAMAGE_HI.get(mode) if mode else None)
    return FOOTWEAR.get(ft or "", FOOTWEAR_DEFAULT["en"]), (DAMAGE.get(mode, mode.lower()) if mode else None)


def _secondary_sentence(fields: dict, lang: str) -> str | None:
    sec = fields.get("secondary_issue") or {}
    mode = sec.get("damage_mode")
    if sec.get("status") != "accepted" or mode in UNKNOWN_VALUES:
        return None
    if lang == "hi":
        return f"हमें यह भी दिखा कि {DAMAGE_HI[mode]}।" if mode in DAMAGE_HI else None
    return f"I also noticed that {DAMAGE.get(mode, mode.lower())}."


def _thanks(lang: str, new_photo: bool) -> str:
    if new_photo:
        return "फ़ोटो के लिए धन्यवाद!" if lang == "hi" else "Thanks for the photo!"
    return "धन्यवाद!" if lang == "hi" else "Thanks!"


def _seen(fields: dict, lang: str) -> str:
    footwear, what = _damage(fields, lang)
    if lang == "hi":
        seen = f"{footwear} में हमें यह दिख रहा है: {what}।" if what else f"हमने {footwear} को ध्यान से देखा।"
    else:
        seen = f"Here's what I can see on your {footwear}: {what}." if what else f"I've had a good look at your {footwear}."
    secondary = _secondary_sentence(fields, lang)
    return seen + (" " + secondary if secondary else "")


# ---------------------------------------------------------------- the diagnosis reply
def diagnosis(result: dict, lang: str = "en", new_photo: bool = True) -> str:
    """The reply to one diagnosis: an answer (accept / cobbler) or a request for a better or closer photo."""
    lang = lang if lang in ("en", "hi") else "en"
    fields, action = result["fields"], result["decision"]["action"]
    hi = lang == "hi"

    if action == "better_photo":
        status = (fields.get("image_status") or {}).get("value")
        en_text, hi_text = BETTER_PHOTO.get(status, BETTER_PHOTO_DEFAULT)
        return hi_text if hi else en_text

    if action == "ask_problem":
        if hi:
            return ("फ़ोटो के लिए धन्यवाद! इसमें हमें कोई खराबी नहीं दिखी। क्या आप उस हिस्से की पास से फ़ोटो भेज "
                    "सकते हैं जिसमें समस्या है?")
        return ("Thanks for the photo! I couldn't spot any damage in it. "
                "Could you send a close-up photo of the part that has the problem?")

    footwear, what = _damage(fields, lang)
    if action == "follow_up":
        # not sure enough about something that decides the fix -> ask for a better look
        if hi:
            seen = (f"ऐसा लग रहा है कि {what}, लेकिन कोई उपाय बताने से पहले हम पक्का होना चाहते हैं।" if what
                    else f"{footwear} में क्या खराबी है, यह पक्का होने के बाद ही हम कोई उपाय बताएँगे।")
        else:
            seen = (f"It looks like {what}, but I want to be sure before suggesting a fix." if what
                    else f"I want to be sure what's wrong with your {footwear} before suggesting a fix.")
        return "\n\n".join([_thanks(lang, new_photo), seen, CLOSER_PHOTO[1] if hi else CLOSER_PHOTO[0]])

    glue_value = _known(fields, "glue_fix_possible") or ""
    glue = (GLUE_HI if hi else GLUE).get(glue_value)
    lines = [_thanks(lang, new_photo), _seen(fields, lang)]
    if action == "cobbler":
        # clear cobbler case: no more questions, no product
        lines.append(glue or ("इसे मोची के पास ले जाना बेहतर रहेगा।" if hi else "It's best taken to a cobbler."))
        return "\n\n".join(lines)

    # accept: every field that decides the fix is confident
    if glue:
        lines.append(glue)
    lines.append(SOLUTION_PLACEHOLDER[lang])
    return "\n\n".join(lines)


# ---------------------------------------------------------------- conversation messages
def language_question() -> str:
    """Sent with two buttons (English / हिंदी). In both languages, since none is chosen yet."""
    return _both(
        "Hello! 👋 Welcome to the footwear repair helpline. Which language would you like to chat in?\n"
        "You can change it any time by typing English or Hindi.",
        "नमस्ते! 👋 फुटवियर रिपेयर हेल्पलाइन में आपका स्वागत है। आप किस भाषा में बात करना चाहेंगे?\n"
        "आप कभी भी English या Hindi लिखकर भाषा बदल सकते हैं।")


def change_language(word_lang: str) -> str:
    """Sent with the two language buttons when the customer types "language" / "भाषा". Shown in the language of
    the word they typed."""
    return _pick(word_lang if word_lang in ("en", "hi") else "en", "🌐 Change language", "🌐 भाषा बदलें")


def language_changed(lang: str) -> str:
    return _pick(lang, "Okay, I'll reply in English from now on.", "ठीक है, अब से हम हिंदी में जवाब देंगे।")


def ask_photo(lang: str | None) -> str:
    """Right after the language is chosen, when no photo has been sent yet."""
    return _pick(lang,
                 "Please send a photo of the footwear that needs fixing.",
                 "कृपया जिस जूते या चप्पल को ठीक करना है, उसकी फ़ोटो भेजें।")


def need_photo(lang: str | None) -> str:
    """A text message (a description, or anything else) before any usable photo."""
    return _pick(lang,
                 "To help, I need to see it: please send a photo of the footwear that needs fixing.",
                 "मदद के लिए हमें उसे देखना होगा: कृपया जिस जूते या चप्पल को ठीक करना है, उसकी फ़ोटो भेजें।")


def please_wait(lang: str | None) -> str:
    """'Please wait' message while the model works. It does not start the 5-minute timer."""
    return _pick(lang, "Got it, taking a look… 👀", "ठीक है, हम देख रहे हैं… 👀")


def voice_or_video(lang: str | None) -> str:
    return _pick(lang,
                 "Sorry, I can't open voice notes or videos yet. Please send a photo of the footwear.",
                 "माफ़ कीजिए, हम अभी वॉइस नोट या वीडियो नहीं खोल सकते। कृपया जूते या चप्पल की फ़ोटो भेजें।")


def tries_used_up(lang: str | None, voice: bool = False) -> str:
    """After the last allowed try. The conversation closes right after this message."""
    en = ("Sorry, I couldn't see the problem clearly enough after a few tries. Please try again with a clear "
          "picture: good light, phone held steady, close up on the damaged part.")
    hi = ("माफ़ कीजिए, कुछ कोशिशों के बाद भी हम समस्या साफ़ नहीं देख पाए। कृपया एक साफ़ फ़ोटो के साथ फिर से "
          "कोशिश करें: अच्छी रोशनी में, फ़ोन स्थिर रखकर, खराब हिस्से के पास से।")
    if voice:
        en = "Sorry, I can't open voice notes or videos yet. " + en.removeprefix("Sorry, ")
        hi = "माफ़ कीजिए, हम अभी वॉइस नोट या वीडियो नहीं खोल सकते। " + hi.removeprefix("माफ़ कीजिए, ")
    return _pick(lang, en, hi)


def after_answer(lang: str | None) -> str:
    """The customer writes after the answer (steps or cobbler). Free questions are not answered yet."""
    return _pick(lang,
                 "My answer is in the message above. If there's another problem with your footwear, "
                 "please send a photo of it.",
                 "हमारा जवाब ऊपर वाले मैसेज में है। अगर जूते या चप्पल में कोई और समस्या है, तो कृपया उसकी फ़ोटो भेजें।")


def closing(lang: str | None) -> str:
    """Sent when the customer hasn't replied for 5 minutes. The bot then forgets the conversation."""
    return _pick(lang,
                 "I'm closing this chat as there's been no reply. Thanks for contacting the footwear helpline! "
                 "Say hi any time to start again.",
                 "कोई जवाब न आने की वजह से हम यह चैट बंद कर रहे हैं। फुटवियर हेल्पलाइन से संपर्क करने के लिए "
                 "धन्यवाद! दोबारा शुरू करने के लिए कभी भी Hi लिखें।")


def error(exc: Exception | None = None, lang: str | None = "en") -> str:
    # the technical error is stored with the diagnosis and shown on the dashboard, not to the customer
    return _pick(lang,
                 "Sorry, something went wrong on our side while looking at your photo. Please try sending it again.",
                 "माफ़ कीजिए, आपकी फ़ोटो देखते समय हमारी तरफ़ से कुछ गड़बड़ हो गई। कृपया उसे फिर से भेजें।")


def type_not_supported(kind: str = "", lang: str | None = "en") -> str:
    return _pick(lang,
                 "Sorry, I can't open that kind of message. Please send a photo of the footwear that needs fixing.",
                 "माफ़ कीजिए, हम इस तरह का मैसेज नहीं खोल सकते। कृपया जिस जूते या चप्पल को ठीक करना है, उसकी "
                 "फ़ोटो भेजें।")


def media_failed(lang: str | None = "en") -> str:
    return _pick(lang, "Sorry, I couldn't download that photo. Please send it again.",
                 "माफ़ कीजिए, हम वह फ़ोटो डाउनलोड नहीं कर पाए। कृपया उसे फिर से भेजें।")
