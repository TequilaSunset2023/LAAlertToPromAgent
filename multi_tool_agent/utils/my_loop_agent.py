from google.adk.agents import LoopAgent, BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from typing import AsyncGenerator, Optional
from typing_extensions import override

class MyLoopAgent(LoopAgent):
  
  @override
  async def _run_async_impl(
      self, ctx: InvocationContext
  ) -> AsyncGenerator[Event, None]:
    times_looped = 0
    while not self.max_iterations or times_looped < self.max_iterations:
      for sub_agent in self.sub_agents:
        async for event in sub_agent.run_async(ctx):
          if event.actions.escalate:
            event.actions.escalate = False  # Reset escalate action
            yield event
            return
          else:
            yield event
      times_looped += 1
    return
