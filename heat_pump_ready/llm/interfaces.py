"""Model-neutral inference contracts with explicit lifecycle and image capability."""
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple
from ..contracts import Attachment

class RunnerError(RuntimeError):
    """Expected inference or structured-response failure, safe to expose as unavailable."""

@dataclass(frozen=True)
class LLMRequest:
    """Prompt and optional evidence, JSON grammar and generation token budget."""
    prompt: str
    attachments: Tuple[Attachment, ...] = ()
    json_schema: Optional[str] = None
    max_tokens: int = 600

@dataclass(frozen=True)
class LLMResponse:
    """Raw response and model provenance; schema validation belongs to the module."""
    text: str
    model: str

class LLMRunner(Protocol):
    """Interchangeable synchronous adapter; invoked outside browser event handling."""
    supports_images: bool

    def start(self) -> None:
        """Explicitly initialize model resources."""
        ...

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Return a response or raise RunnerError; never invent an extraction fallback."""
        ...

    def close(self) -> None:
        """Release owned resources."""
        ...
