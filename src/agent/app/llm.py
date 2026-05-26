from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import Runnable

from app.config import settings
from app.tools import (
    combined_filter_search,
    date_filter_search,
    metadata_filter_search,
    semantic_search,
)

SYSTEM_PROMPT = """You are MemoryLane's search agent. Given a user's natural-language \
query about their photo library, decide which tool to use:

- semantic_search: default for any visual concept ("sunset", "dog at the beach")
- date_filter_search: when the query mentions time only ("last summer", "in 2023")
- metadata_filter_search: when the query mentions camera or location only
- combined_filter_search: when the query mentions BOTH time AND camera/location \
("Paris trip last summer on my Canon") — always prefer this over calling \
date_filter_search and metadata_filter_search separately

You may invoke multiple tools across iterations if results are insufficient.
After reviewing results, decide whether to stop or refine.
"""

_TOOLS = [semantic_search, date_filter_search, metadata_filter_search, combined_filter_search]


def get_llm() -> Runnable[Any, Any]:
    llm = ChatAnthropic(
        model=settings.claude_model,
        api_key=settings.anthropic_api_key,
        temperature=0.0,
    )
    return llm.bind_tools(_TOOLS)
