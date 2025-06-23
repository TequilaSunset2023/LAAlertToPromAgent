import asyncio
import logging
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai.types import Content, Part
from google.adk.agents.invocation_context import InvocationContext
from typing import AsyncGenerator
from typing_extensions import override

logger = logging.getLogger(__name__)

class MyHILAgent(BaseAgent):
    user_state_key: str = "hitl"

    """
        def __init__(self, name: str, description: str, user_state_key: str = "hitl"):
            super().__init__(name=name, description=description)
            self.user_state_key = user_state_key
    """

    @override
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        if ctx.session.app_name not in ctx.session_service.user_state:
            ctx.session_service.user_state[ctx.session.app_name] = {}
        if ctx.session.user_id not in ctx.session_service.user_state[ctx.session.app_name]:
            ctx.session_service.user_state[ctx.session.app_name][ctx.session.user_id] = {}
        
        user_state_key = self.user_state_key

        ctx.session_service.user_state[ctx.session.app_name][ctx.session.user_id][user_state_key] = ""

        while True:
            # Check if hitl state is empty
            if not ctx.session_service.user_state[ctx.session.app_name][ctx.session.user_id][user_state_key]:
                # If empty, sleep for 2 seconds
                logger.debug("Waiting for HITL value to be set... (2 seconds)")
                await asyncio.sleep(2)
            else:
                # If not empty, return the value
                hitl_value = ctx.session_service.user_state[ctx.session.app_name][ctx.session.user_id][user_state_key]
                logger.info(f"Running MyHILAgent with HITL value: {hitl_value}")
                yield Event(
                    author="",
                    content= Content(parts=[Part(text=hitl_value)], role="model")
                )
                return