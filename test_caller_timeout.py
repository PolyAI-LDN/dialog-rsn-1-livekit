import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.modules.setdefault('dotenv',SimpleNamespace(load_dotenv=lambda *a,**kw:None))
sys.modules.setdefault('numpy',SimpleNamespace(ndarray=object))
sys.modules.setdefault('livekit',SimpleNamespace(api=SimpleNamespace(),rtc=SimpleNamespace(Track=object,RemoteParticipant=object,TextStreamReader=object)))
from caller import Caller

class CallerTimeoutTest(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_covers_both_missing_agent_and_unfinished_reply(self):
        for state,loud in [('',0),('thinking',0.1),('speaking',0.1)]:
            with self.subTest(state=state):
                caller=Caller.__new__(Caller)
                caller.last_loud=loud
                now=[0.0]
                async def pause(seconds):
                    now[0]+=seconds
                    await asyncio.sleep(0)
                caller.pause=pause
                caller.agent_state=lambda:state
                with patch('caller.time',SimpleNamespace(monotonic=lambda:now[0])):
                    await asyncio.wait_for(caller.until_agent_finishes(timeout=1),timeout=0.1)
                self.assertLessEqual(now[0],1.2)
