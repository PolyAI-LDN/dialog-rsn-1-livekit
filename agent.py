"""Grand Meridian Hotel front desk: a LiveKit voice agent on Dialog-RSN-1.

    lk agent console agent.py   # talk to it in the terminal, no LiveKit server needed
    uv run agent.py dev         # join rooms on your LiveKit server
"""

import json
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RunContext, cli
from livekit.agents.llm import function_tool
from livekit.plugins import elevenlabs, polyai

from hotel import INSTRUCTIONS, change_checkout_time, look_up_reservation

load_dotenv(Path(__file__).parent / ".env")


class FrontDesk(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=INSTRUCTIONS)

    @function_tool
    async def look_up_reservation(
        self, context: RunContext, confirmation_code: str = "", last_name: str = ""
    ) -> str:
        """Find a reservation by confirmation code or by the guest's last name.

        Args:
            confirmation_code: Confirmation code, for example GM40912.
            last_name: The guest's last name.
        """
        return json.dumps(look_up_reservation(confirmation_code, last_name))

    @function_tool
    async def change_checkout_time(
        self, context: RunContext, confirmation_code: str, new_checkout_time: str
    ) -> str:
        """Change the checkout time. State any fee and get the guest's agreement first.

        Args:
            confirmation_code: Confirmation code, for example GM40912.
            new_checkout_time: 24-hour HH:MM, for example 14:00.
        """
        return json.dumps(change_checkout_time(confirmation_code, new_checkout_time))


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    session = AgentSession(
        # Dialog-RSN-1 hears the caller, decides when they've finished, and streams the reply
        # as text. It replaces the STT, the LLM and the turn detector.
        llm=polyai.realtime.RealtimeModel(),
        # Dialog-RSN-1 doesn't speak, so a TTS voices each reply as it streams.
        tts=elevenlabs.TTS(voice_id="EXAVITQu4vr4xnSDxMaL", model="eleven_flash_v2_5"),
    )

    await session.start(agent=FrontDesk(), room=ctx.room)
    # Dialog-RSN-1 ignores per-reply instructions, so the greeting comes from INSTRUCTIONS.
    await session.generate_reply()


if __name__ == "__main__":
    cli.run_app(server)
