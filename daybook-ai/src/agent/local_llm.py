from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


SYSTEM_PROMPT = """You are Daybook AI, a bounded local assistant.
Use only the records explicitly supplied. Distinguish stored facts from interpretation.
Do not claim current external knowledge. Do not shame the user. Do not imply actions were taken.
You may summarize, explain, recommend, or break work into steps.
For requested task changes, return a JSON proposal only; never directly modify data.
Prohibited: external communication, internet use, command execution, file access, surveillance, productivity scoring, or changing commitments.
"""


class LocalModelError(RuntimeError):
    pass


@dataclass(slots=True)
class LocalModelClient:
    base_url: str
    model: str = "auto"
    timeout: int = 30

    @property
    def models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/models"

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def available_models(self) -> list[str]:
        try:
            response = requests.get(self.models_url, timeout=3)
            response.raise_for_status()
            payload = response.json()
            values = payload.get("data", [])
            models = [item.get("id") for item in values if isinstance(item, dict)]
            return [value for value in models if isinstance(value, str) and value.strip()]
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise LocalModelError(f"Local model discovery failed: {exc}") from exc

    def resolved_model(self) -> str:
        models = self.available_models()
        if not models:
            raise LocalModelError("The local server reported no loaded models.")
        if self.model and self.model not in {"auto", "local-model"}:
            if self.model not in models:
                raise LocalModelError(
                    f"Configured model '{self.model}' is not loaded. Available: {', '.join(models)}"
                )
            return self.model
        return models[0]

    def healthcheck(self, verify_inference: bool = True) -> tuple[bool, str]:
        try:
            model = self.resolved_model()
            if not verify_inference:
                return True, f"Local model server connected. Loaded model: {model}"

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "Answer briefly."},
                    {"role": "user", "content": "Reply with the word ready."},
                ],
                "temperature": 0,
                "max_tokens": 32,
                "chat_template_kwargs": {"enable_thinking": False},
            }
            response = requests.post(self.chat_url, json=payload, timeout=min(self.timeout, 15))
            response.raise_for_status()
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content")
            reasoning = message.get("reasoning_content")
            if not any(isinstance(value, str) and value.strip() for value in (content, reasoning)):
                raise LocalModelError("The server returned no usable completion content.")
            return True, f"Local AI inference verified. Loaded model: {model}"
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, LocalModelError) as exc:
            return False, f"Local AI unavailable or unverified: {exc}"

    def chat(self, user_request: str, context_records: list[dict[str, Any]]) -> str:
        model = self.resolved_model()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"request": user_request, "local_records": context_records},
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 500,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = requests.post(self.chat_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            content = message.get("content")
            reasoning = message.get("reasoning_content")
            value = content if isinstance(content, str) and content.strip() else reasoning
            if not isinstance(value, str) or not value.strip():
                raise LocalModelError("The model returned an empty response.")
            return value.strip()
        except LocalModelError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LocalModelError(f"Local model request failed: {exc}") from exc

    @staticmethod
    def parse_action_proposal(text: str) -> dict:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LocalModelError("The model output was not valid JSON.") from exc
        required = {"action", "requires_confirmation", "proposed_values", "reason"}
        if not isinstance(value, dict) or not required.issubset(value):
            raise LocalModelError("The model output did not match the required proposal schema.")
        if value["requires_confirmation"] is not True:
            raise LocalModelError("The proposal attempted to bypass confirmation.")
        return value
