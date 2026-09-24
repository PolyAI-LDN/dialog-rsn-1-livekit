# A LiveKit voice agent on Dialog-RSN-1

Companion code for *Build a LiveKit voice agent on Dialog-RSN-1*.

A front-desk agent for the fictional Grand Meridian Hotel, built on
[LiveKit Agents](https://docs.livekit.io/agents/). Dialog-RSN-1 hears the caller, decides when
they've finished, and streams the reply as text. ElevenLabs speaks it. There's no separate
speech-to-text, turn detector or LLM.

| File | What it is |
|---|---|
| `agent.py` | The agent: instructions, two tools, and an `AgentSession` with Dialog-RSN-1 and a TTS |
| `dialog_rsn_1.py` | `RealtimeModel`: LiveKit's OpenAI Realtime plugin, adjusted for Dialog-RSN-1. Copy it into your own agent |
| `hotel.py` | Instructions and in-memory demo bookings |
| `caller.py` | A scripted caller that joins a room and speaks the WAVs in `samples/`, including a barge-in |

## Run it

You need Python 3.10 or later, [uv](https://docs.astral.sh/uv/) and the
[LiveKit CLI](https://docs.livekit.io/intro/basics/cli/) (`brew install livekit-cli`).

```bash
cp .env.example .env         # add DIALOGUE_API_KEY and ELEVEN_API_KEY
uv sync
lk agent console agent.py    # talk to it through your microphone and speakers
```

Add `--text` to type instead. Text mode turns TTS off, so only Dialog-RSN-1 and the tools run.

Try "Can you look up booking GM40912?", then ask to check out at two. Talk over a long answer
and it stops.

## Run it in a LiveKit room

Point `LIVEKIT_URL`, `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET` in `.env` at your LiveKit
Cloud project, or run a local server with `livekit-server --dev` (`brew install livekit`) and
keep the defaults from `.env.example`. Then:

```bash
uv run agent.py dev   # terminal 1: the agent joins every new room
uv run caller.py      # terminal 2: a scripted caller, no microphone needed
```

```text
[  7.4s] agent : Hello, Grand Meridian Hotel. How can I help you today?
[ 14.8s] caller: Hi, can you look up booking G M four zero nine one two please?
[ 22.0s] agent : I've found your booking, Amara. You're currently scheduled to check out at 11:00 on September 30th. What would you like to change?
[ 31.6s] caller: Can you tell me everything about my booking and describe the hotel for me in detail?
[ 34.3s] agent : I can tell you about your booking - you have a Deluxe King room, checking out
[ 39.4s] caller: Sorry, stop, stop. Actually, what time is checkout?
[ 44.0s] agent : Your current checkout time is 11:00 AM on September 30th. Would you like to change that?
```

The cut-off line is the barge-in: the transcript holds only what the caller heard. The agent's
side of the call is saved to `call.wav`.

## Why `dialog_rsn_1.py` exists

LiveKit's `openai.realtime.RealtimeModel` speaks the same protocol as Dialog-RSN-1. Point it at
`https://api.us.poly.ai/v1` unchanged, though, and it breaks three ways:

| Symptom | Cause |
|---|---|
| `'audio.output' is not supported by this service` | The plugin always sends a voice and OpenAI's turn-detection tuning. Dialog-RSN-1 rejects the whole `session.update`, instructions included |
| `generate_reply timed out` | The plugin waits for `response.metadata` to be echoed back. Dialog-RSN-1 doesn't echo it |
| `function_call_output.call_id=... does not match the pending tool call`, then `generation_failed` on every turn | The plugin shortens call ids longer than 32 characters. Dialog-RSN-1's are 37 |

`dialog_rsn_1.RealtimeModel` fixes those three and asks for text replies. It subclasses the
plugin's internals, so `pyproject.toml` pins `livekit-agents` to the 1.8 series it was tested on.
