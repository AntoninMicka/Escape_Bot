from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


Payload = dict[str, Any]


@dataclass(slots=True)
class Message:
    type: str
    payload: Payload = field(default_factory=dict)
    request_id: str | None = None
    operation_id: str | None = None

    @classmethod
    def from_json(cls, data: Payload) -> "Message":
        message_type = data.get("type")
        if not isinstance(message_type, str) or not message_type:
            raise ValueError("Message field 'type' must be a non-empty string.")

        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("Message field 'payload' must be an object.")

        request_id = data.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            raise ValueError("Message field 'request_id' must be a string.")

        operation_id = data.get("operation_id")
        if operation_id is not None and (
            not isinstance(operation_id, str) or not (1 <= len(operation_id) <= 128)
        ):
            raise ValueError("Message field 'operation_id' must be a string with 1 to 128 characters.")

        return cls(
            type=message_type,
            payload=payload,
            request_id=request_id,
            operation_id=operation_id,
        )

    def to_json(self) -> Payload:
        data: Payload = {"type": self.type, "payload": self.payload}
        if self.request_id:
            data["request_id"] = self.request_id
        if self.operation_id:
            data["operation_id"] = self.operation_id
        return data


def reply(message_type: str, payload: Payload, request: Message | None = None) -> Message:
    return Message(
        type=message_type,
        payload=payload,
        request_id=request.request_id if request else None,
        operation_id=request.operation_id if request else None,
    )
