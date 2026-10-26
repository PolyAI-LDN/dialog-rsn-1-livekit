# A LiveKit voice agent on Dialog-RSN-1

Companion code for *Build a LiveKit voice agent on Dialog-RSN-1*.

A front-desk agent for the fictional Grand Meridian Hotel, built on
[LiveKit Agents](https://docs.livekit.io/agents/). Dialog-RSN-1 hears the caller, decides when
they've finished, and streams the reply as text. ElevenLabs speaks it. There's no separate
speech-to-text, turn detector or LLM.

| File | What it is |
|---|---|
| `agent.py` | The agent: instructions, two tools, and an `AgentSession` with Dialog-RSN-1 and a TTS |
| `hotel.py` | Instructions and in-memory demo bookings |
| `caller.py` | A scripted caller that joins a room and speaks the WAVs in `samples/`, including a barge-in |

## Run it

You need Python 3.10 or later, [uv](https://docs.astral.sh/uv/) and the
[LiveKit CLI](https://docs.livekit.io/intro/basics/cli/) (`brew install livekit-cli`).

```bash
cp .env.example .env         # add POLY_API_KEY and ELEVEN_API_KEY
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

## Dialog-RSN-1 on LiveKit's OpenAI plugin

Dialog-RSN-1 speaks the OpenAI Realtime protocol, so the agent uses LiveKit's own OpenAI plugin,
pointed at Dialog-RSN-1's URL and key:

```python
from livekit.plugins import openai

llm = openai.realtime.RealtimeModel(
    base_url=os.environ.get("DIALOG_REALTIME_URL", "wss://api.studio.poly.ai/v1"),
    api_key=os.environ["POLY_API_KEY"],
    model="dialog-rsn-1",
    modalities=["text"],
)
```

`modalities=["text"]` matters: the plugin's default asks for audio, so Dialog-RSN-1 would speak
the replies in its own voice and LiveKit would skip your TTS. For a key from `studio.us.poly.ai`,
set `DIALOG_REALTIME_URL=wss://api.us.poly.ai/v1`.

To add Dialog-RSN-1 to your own agent, install the plugin with `uv add "livekit-agents[openai]~=1.8.3"`
and see [Add Dialog-RSN-1 to an existing LiveKit agent](https://docs.poly.ai/dialog-rsn-1/guides/livekit#add-dialog-rsn-1-to-an-existing-livekit-agent)
in the guide. [Settings that matter](https://docs.poly.ai/dialog-rsn-1/guides/livekit#settings-that-matter)
lists the few options to set or avoid, and how to send Dialog-RSN-1's own fields.
