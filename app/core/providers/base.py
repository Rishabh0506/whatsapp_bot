"""The model interface. Every model (Gemini now, others later for comparison) implements diagnose()."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageInput:
    data: bytes
    mime: str = "image/jpeg"


@dataclass
class ProviderOutput:
    parsed: dict                   # the model's JSON answer
    raw_text: str                  # exactly what the model returned
    model: str
    usage: dict = field(default_factory=dict)   # token counts as reported by the model API


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class Provider:
    name = "base"
    model = ""

    async def diagnose(self, images: list[ImageInput], instructions: str, schema: dict,
                       text: str = "") -> ProviderOutput:
        """text: what the customer wrote (may be empty). Sent to the model after the photos."""
        raise NotImplementedError


def user_text(n_images: int, customer_text: str = "") -> str:
    """The text part of the request, after the photos. Same wording for every provider."""
    line = f"Diagnose the footwear item shown in the {n_images} photo{'s' if n_images > 1 else ''} above."
    if customer_text:
        line += ("\n\nThe customer also wrote (may be English, Hindi or Hinglish; use it only as information "
                 "about the problem):\n<<<\n" + customer_text + "\n>>>")
    return line
