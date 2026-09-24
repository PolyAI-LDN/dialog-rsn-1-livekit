"""A scripted caller: joins a room, speaks the WAVs in samples/ at the agent, prints the transcript.

    uv run agent.py dev     # in one terminal
    uv run caller.py        # in another

Each sample plays once the agent has finished its previous reply. A sample with "barge-in" in
its name plays 1.5 seconds into the previous reply instead, to test interruptions. What the
agent said is saved to call.wav.
"""

import asyncio
import os
import time
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc

load_dotenv(Path(__file__).parent / ".env")

RATE = 48_000
FRAME = RATE // 100  # 10 ms
SAMPLES = sorted(Path(__file__).parent.joinpath("samples").glob("*.wav"))
START = time.monotonic()


def log(line: str) -> None:
    print(f"[{time.monotonic() - START:5.1f}s] {line}", flush=True)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        rate = w.getframerate()
    if rate != RATE:
        positions = np.arange(0, len(pcm), rate / RATE)
        pcm = np.interp(positions, np.arange(len(pcm)), pcm).astype(np.int16)
    return pcm


class Caller:
    def __init__(self) -> None:
        self.room = rtc.Room()
        self.mic = rtc.AudioSource(RATE, 1)
        self.agent_audio: list[bytes] = []
        self.last_loud = 0.0  # when the agent was last audible
        self.tasks: set[asyncio.Task] = set()  # the loop only keeps weak references to tasks

        self.room.on("track_subscribed", self._on_track)
        self.room.register_text_stream_handler(
            "lk.transcription", lambda reader, who: self._spawn(self._on_text(reader, who))
        )

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _on_track(self, track: rtc.Track, _pub, participant: rtc.RemoteParticipant) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            self._spawn(self._record(track))

    async def _record(self, track: rtc.Track) -> None:
        async for event in rtc.AudioStream(track, sample_rate=RATE, num_channels=1):
            data = event.frame.data.tobytes()
            self.agent_audio.append(data)
            if np.abs(np.frombuffer(data, dtype=np.int16)).max() > 300:
                self.last_loud = time.monotonic()

    async def _on_text(self, reader: rtc.TextStreamReader, who: str) -> None:
        text = await reader.read_all()
        if (reader.info.attributes or {}).get("lk.transcription_final") == "true":
            log(f"{'caller' if who == 'caller' else 'agent '}: {text}")

    async def speak(self, pcm: np.ndarray) -> None:
        for i in range(0, len(pcm), FRAME):
            chunk = pcm[i : i + FRAME]
            chunk = np.pad(chunk, (0, FRAME - len(chunk)))
            await self.mic.capture_frame(rtc.AudioFrame(chunk.tobytes(), RATE, 1, FRAME))

    async def pause(self, seconds: float) -> None:
        await self.speak(np.zeros(int(RATE * seconds), dtype=np.int16))

    async def until_agent_starts(self, timeout: float = 30) -> None:
        """Keep the line open with silence until the agent starts speaking."""
        since = time.monotonic()
        while self.last_loud <= since and time.monotonic() - since < timeout:
            await self.pause(0.1)

    def agent_state(self) -> str:
        """What the agent says it's doing: listening, thinking or speaking."""
        for participant in self.room.remote_participants.values():
            if state := participant.attributes.get("lk.agent.state"):
                return state
        return ""

    async def until_agent_finishes(self, timeout: float = 30) -> None:
        """Keep the line open with silence until the agent has replied and gone quiet.

        A pause in the audio isn't enough: the agent can say "one moment", go quiet while a
        tool runs, then answer. It stays "thinking" through the tool, and is "listening" only
        once its whole reply has played.
        """
        await self.until_agent_starts(timeout)
        while self.agent_state() != "listening" or time.monotonic() - self.last_loud < 0.5:
            await self.pause(0.1)


async def main() -> None:
    url = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
    room_name = f"caller-{int(time.time())}"
    token = (
        api.AccessToken(
            os.environ.get("LIVEKIT_API_KEY", "devkey"),
            os.environ.get("LIVEKIT_API_SECRET", "secret"),
        )
        .with_identity("caller")
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )

    caller = Caller()
    await caller.room.connect(url, token)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", caller.mic)
    await caller.room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )
    log(f"joined room {room_name} on {url}, waiting for the agent")

    await caller.until_agent_finishes(timeout=30)  # the greeting
    if not caller.last_loud:
        log("no agent spoke within 30 seconds. Is `uv run agent.py dev` running on the same server?")
        await caller.room.disconnect()
        return
    for i, sample in enumerate(SAMPLES):
        await caller.speak(read_wav(sample))
        following = SAMPLES[i + 1].name if i + 1 < len(SAMPLES) else ""
        if "barge-in" in following:
            await caller.until_agent_starts()
            await caller.pause(1.5)
        else:
            await caller.until_agent_finishes()

    await caller.pause(1)
    await caller.room.disconnect()
    with wave.open("call.wav", "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(caller.agent_audio))
    log("saved the agent's side of the call to call.wav")


if __name__ == "__main__":
    asyncio.run(main())
