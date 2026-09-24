"""Dialog-RSN-1 as a LiveKit Agents realtime model.

LiveKit's OpenAI Realtime plugin already speaks the protocol. Pointed at
Dialog-RSN-1 as shipped, it breaks in three places:

1. Every `session.update` carries `audio.output` and OpenAI's turn-detection
   tuning. Dialog-RSN-1 rejects those fields, and a rejected update applies
   nothing, so the agent's instructions go with them.
2. `generate_reply` waits for the server to echo `response.metadata`.
   Dialog-RSN-1 doesn't, so every call times out after 10 seconds.
3. Tool results go back under a shortened `call_id`, because OpenAI caps ids at
   32 characters and Dialog-RSN-1's are longer. The server doesn't recognise the
   shortened id, and every later reply fails.

This module fixes all three and asks for text replies. Everything else is the
stock plugin, so this file is pinned to the LiveKit Agents minor version it was
tested on (see pyproject.toml).
"""

from __future__ import annotations

import os
from collections import deque
from contextlib import suppress
from typing import Any

from livekit.agents.llm._realtime.openai_utils import _shorten_call_id
from livekit.plugins import openai
from openai.types.realtime.realtime_audio_input_turn_detection import ServerVad
from pydantic import BaseModel

DEFAULT_BASE_URL = "https://api.us.poly.ai/v1"


class RealtimeModel(openai.realtime.RealtimeModel):
    """Dialog-RSN-1 speech in, streamed text out. Pair it with a TTS in AgentSession."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        api_key = api_key or os.environ.get("DIALOGUE_API_KEY")
        if not api_key:
            # Checked here because the plugin would otherwise fall back to OPENAI_API_KEY and
            # send that key to Dialog-RSN-1.
            raise ValueError("Set DIALOGUE_API_KEY, or pass api_key, to a Dialog-RSN-1 API key.")
        super().__init__(
            model="dialog-rsn-1",
            modalities=["text"],
            api_key=api_key,
            base_url=base_url or os.environ.get("DIALOGUE_BASE_URL", DEFAULT_BASE_URL),
            # The turn boundary is a model judgment here, not a silence timer, so
            # create_response is the only turn-detection field the service reads.
            turn_detection=ServerVad(type="server_vad", create_response=True),
            **kwargs,
        )

    def session(self, *, turn_detection_disabled: bool = False) -> RealtimeSession:
        sess = RealtimeSession(self, turn_detection_disabled=turn_detection_disabled)
        self._sessions.add(sess)
        return sess


class RealtimeSession(openai.realtime.RealtimeSession):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # event_ids of response.create events sent and not yet answered, oldest first
        self._unanswered_creates: deque[str] = deque()
        # the plugin's shortened form of each server call_id, mapped back to the original
        self._call_ids: dict[str, str] = {}
        super().__init__(*args, **kwargs)
        # Fired just before each event goes on the socket, on the reconnect path too, so the
        # queue holds ids in the order the server receives them.
        self.on("openai_client_event_queued", self._on_event_sent)
        # A new connection answers nothing sent on the old one. The plugin fails those
        # generate_reply calls itself; forget their ids so they can't claim a new response.
        self.on("session_reconnected", lambda _: self._unanswered_creates.clear())

    def _wrap_session_update(self, event_id: str, session: Any) -> dict[str, Any]:
        # Every session.update is built here, including the one the plugin sends straight to
        # the socket when it reconnects, so this is the one place that catches them all.
        event = super()._wrap_session_update(event_id, session)
        if isinstance(event, BaseModel):
            event = event.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=False)
        _strip_unsupported(event["session"])
        return event

    def send_event(self, event: Any) -> None:
        if isinstance(event, BaseModel):
            event = event.model_dump(by_alias=True, exclude_unset=True, exclude_defaults=False)
        if event.get("type") == "conversation.item.create":
            item = event.get("item") or {}
            if item.get("call_id") in self._call_ids:
                item["call_id"] = self._call_ids[item["call_id"]]
        super().send_event(event)

    def _on_event_sent(self, event: dict[str, Any]) -> None:
        if event.get("type") == "response.create" and event.get("event_id"):
            self._unanswered_creates.append(event["event_id"])

    def generate_reply(self, **kwargs: Any) -> Any:
        fut = super().generate_reply(**kwargs)
        event_id = next(k for k, f in self._response_created_futures.items() if f is fut)

        def _on_done(f: Any) -> None:
            # The server answers each response.create at once, so one unanswered after the
            # plugin's 10 second timeout never will be. Left in the queue, it would claim the
            # next response, and every reply after that would go to the request before it.
            if not f.cancelled() and f.exception() is not None:
                with suppress(ValueError):
                    self._unanswered_creates.remove(event_id)

        fut.add_done_callback(_on_done)
        return fut

    def _handle_function_call(self, item: Any) -> None:
        # OpenAI caps call_id at 32 characters and the plugin hashes anything longer before
        # sending it back. Dialog-RSN-1's call_ids are longer, so the tool result would come
        # back under an id the server doesn't know, and the next turn would fail. Remember
        # each id so send_event can restore it.
        self._call_ids[_shorten_call_id(item.call_id)] = item.call_id
        super()._handle_function_call(item)

    def _handle_response_created(self, event: Any) -> None:
        # The plugin matches each response.created to the generate_reply that asked for it
        # through response.metadata. Dialog-RSN-1 doesn't echo metadata back, so without this
        # every generate_reply times out after 10 seconds. The server answers each
        # response.create as it arrives, with response.created or an error that names it, so
        # the oldest unanswered one is the one this response belongs to.
        # One race remains. If the server starts its own reply to the caller's turn just
        # before a response.create reaches it, that reply takes the id here and the create is
        # refused. The reply is still spoken, unless that generate_reply was already
        # cancelled, in which case it is dropped.
        if not event.response.metadata and self._unanswered_creates:
            event.response.metadata = {"client_event_id": self._unanswered_creates.popleft()}
        super()._handle_response_created(event)

    def _handle_conversion_item_added(self, event: Any) -> None:
        # The server echoes the plugin's "root" placeholder for the first item instead of null.
        if event.previous_item_id == "root":
            event.previous_item_id = None
        super()._handle_conversion_item_added(event)

    def _handle_error(self, event: Any) -> None:
        # A rejected response.create gets an error instead of a response.created.
        with suppress(ValueError):
            self._unanswered_creates.remove(event.error.event_id)
        super()._handle_error(event)


def _strip_unsupported(session: dict[str, Any]) -> None:
    """Remove the session fields Dialog-RSN-1 rejects, in place."""
    session.pop("reasoning", None)
    audio = session.get("audio")
    if not audio:
        return
    audio.pop("output", None)
    audio_in = audio.get("input") or {}
    audio_in.pop("noise_reduction", None)
    turn_detection = audio_in.get("turn_detection")
    if turn_detection:
        audio_in["turn_detection"] = {
            "type": "server_vad",
            "create_response": turn_detection.get("create_response", True),
        }
    if not audio_in:
        audio.pop("input", None)
    if not audio:
        session.pop("audio", None)
