"""The reader who does not know the answer.

Every other checker in this repository knows the outline, the registry and the
recaps, which means they cannot see the failure a stranger sees on a first read:
*a person on the page whose name is missing.* A deterministic tripwire can catch
a role-and-number introduction, but only a reader with no prior knowledge can
catch referent confusion in general.

So this agent gets the chapter text and nothing else. It is deliberately starved:
no outline, no character cards, no story-so-far. Its confusions are evidence.
"""

from typing import List

from pydantic import BaseModel, Field

from generator.json_parser import generate_validated
from prompts.system_prompts import COLD_READ_PROMPT


class ColdReadReport(BaseModel):
    who_is_on_stage: List[str] = Field(default_factory=list, description="People the chapter names, in order")
    what_changed: List[str] = Field(default_factory=list, description="What is different by the end")
    unresolved_references: List[str] = Field(default_factory=list, description="People or things referred to but never identified")
    questions: List[str] = Field(default_factory=list, description="What a reader would have to ask")

    @property
    def is_confused(self) -> bool:
        return bool(self.unresolved_references)


class ColdReaderAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    def read(self, chapter_number: int, chapter_text: str) -> ColdReadReport:
        prompt = (
            f"TASK: cold read\n"
            f"You are reading chapter {chapter_number} of an unpublished manuscript. "
            f"You have not been told anything about the book, and you cannot ask the author.\n\n"
            f"---\n{chapter_text}\n---\n\n"
            f"Answer only from what is on the page. If you cannot tell who a person is, "
            f"say so in unresolved_references using the words the page uses."
        )
        return generate_validated(self.llm, prompt, COLD_READ_PROMPT, ColdReadReport)
