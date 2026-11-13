"""Push delivery. The provider is pluggable so tests and local runs need no network."""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

logger = logging.getLogger("schooltrack.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


@dataclass(frozen=True, slots=True)
class PushMessage:
    token: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PushResult:
    ok: bool
    error: str | None = None


class PushSender(Protocol):
    def send(self, messages: list[PushMessage]) -> list[PushResult]: ...


class LogSender:
    """Development default: logs instead of sending (never logs the token itself)."""

    def send(self, messages: list[PushMessage]) -> list[PushResult]:
        for message in messages:
            logger.info("push (log only): %s - %s", message.title, message.body)
        return [PushResult(ok=True) for _ in messages]


class ExpoPushSender:
    """Expo push service (the mobile app is built with Expo)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=10)

    def send(self, messages: list[PushMessage]) -> list[PushResult]:
        payload = [
            {"to": m.token, "title": m.title, "body": m.body, "data": m.data, "sound": "default"}
            for m in messages
        ]
        try:
            response = self.client.post(EXPO_PUSH_URL, json=payload)
            response.raise_for_status()
            tickets = response.json().get("data", [])
        except (httpx.HTTPError, ValueError) as exc:
            return [PushResult(ok=False, error=f"{type(exc).__name__}: {exc}") for _ in messages]
        results = []
        for index in range(len(messages)):
            ticket = tickets[index] if index < len(tickets) else {}
            if ticket.get("status") == "ok":
                results.append(PushResult(ok=True))
            else:
                results.append(PushResult(ok=False, error=str(ticket.get("message", "no ticket"))))
        return results


def sender_for(provider: str) -> PushSender:
    return ExpoPushSender() if provider == "expo" else LogSender()
