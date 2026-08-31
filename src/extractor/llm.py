"""The LLM seam.

EVERY call to a language model in this service must go through `LLMClient`.
That is not a style preference: the grading harness replaces this client with
its own implementation, and anything that reaches a model by another route is
invisible to it. A service whose call count stays at zero under our client,
while the shipped client shows calls, is treated as having bypassed the seam.

Three implementations ship:

    StubClient      the default. No network, no key, deterministic. `make score`
                    works out of the box.
    OpenAIClient    used when OPENAI_API_KEY is set.
    RecordingClient a wrapper that counts calls and latency. The throughput axis
                    is measured from its counters, so leave it in place.

The seam is deliberately narrow: one method, text in, text out, explicit
timeout. If you need structure, parse it on your side and handle the case where
the parse fails, because it will.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol


class LLMError(RuntimeError):
    """Any failure to obtain a usable completion. Callers must expect it."""


class LLMClient(Protocol):
    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        """Return the model's raw text. Raises LLMError on any failure."""
        ...


# ---------------------------------------------------------------------------


class StubClient:
    """Deterministic canned responses. The default so the service runs offline.

    It answers the header-mapping prompt with a plausible guess derived from
    the prompt text itself. It is not smart and is not meant to be.
    """

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        self.calls += 1
        lowered = prompt.lower()

        # Dispatch on the shape of the prompt, so the stub is a plausible stand-in
        # for a real model rather than a single canned string.
        if "normalise this mexican insurance vehicle use" in lowered:
            return prompt.rsplit(":", 1)[-1].strip().upper()

        mapping = {}
        for canonical, needles in (
            ("vin", ("niv", "vin", "serie")),
            ("plate", ("placa", "plate")),
            ("brand", ("marca", "brand", "make", "armadora")),
            ("model", ("modelo", "model", "descripcion")),
            ("year", ("año", "ano", "year", "mod")),
            ("value_mxn", ("valor", "suma", "value", "insured")),
            ("use", ("uso", "use", "servicio")),
        ):
            for needle in needles:
                if needle in lowered:
                    mapping[canonical] = needle
                    break
        return json.dumps({"header_row": 0, "mapping": mapping})


class OpenAIClient:
    """Used when OPENAI_API_KEY is present. Any provider is fine; swap freely."""

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature
        self._client = None

    def _ensure(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - depends on the env
                raise LLMError("openai package is not installed") from exc
            self._client = OpenAI()
        return self._client

    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        try:
            response = self._ensure().chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_s,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - the seam normalises everything
            raise LLMError(str(exc)) from exc


@dataclass
class RecordingClient:
    """Counts calls and time spent. The throughput axis reads these counters.

    Wrap whatever you use. Leaving it out does not help you: the harness wraps
    your client itself, and a submission whose counters disagree with the
    harness's own is read as an attempt to route around the seam.
    """

    inner: LLMClient
    calls: int = 0
    failures: int = 0
    seconds: float = 0.0
    prompts: list[str] = field(default_factory=list)

    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        started = time.perf_counter()
        try:
            return self.inner.complete(prompt, timeout_s=timeout_s)
        except Exception:
            self.failures += 1
            raise
        finally:
            self.seconds += time.perf_counter() - started

    def snapshot(self) -> dict[str, float | int]:
        return {"calls": self.calls, "failures": self.failures, "seconds": round(self.seconds, 3)}


def default_client() -> LLMClient:
    """OpenAI when a key is present, the offline stub otherwise."""
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIClient()
    return StubClient()
