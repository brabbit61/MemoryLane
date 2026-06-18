from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import Runnable

from app.config import settings
from app.tools import search_photos

SYSTEM_PROMPT = """You are MemoryLane's search agent. Given a user's natural-language \
query about their photo library, call search_photos to find relevant results.

Supply filters only when the query mentions them:
- Time ("last summer", "in 2023"): set start_date and end_date
- Camera brand ("my Canon"): set camera_make
- Geographic area: set min/max latitude and longitude

You may invoke the tool multiple times across iterations if results are insufficient.
After reviewing results, decide whether to stop or refine.
"""

_TOOLS = [search_photos]


def get_llm() -> Runnable[Any, Any]:
    llm = ChatAnthropic(
        model=settings.claude_model,
        api_key=settings.anthropic_api_key,
        temperature=0.0,
    )
    return llm.bind_tools(_TOOLS)
