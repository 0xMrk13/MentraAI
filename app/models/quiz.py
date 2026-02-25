from dataclasses import dataclass
from typing import List

@dataclass
class QuizQuestion:
    question: str
    choices: List[str]
    answer_index: int
    explanation: str

    def __post_init__(self):
        if len(self.choices) not in (3, 4):
            raise ValueError("QuizQuestion must have 3 or 4 choices")
        if not (0 <= self.answer_index < len(self.choices)):
            raise ValueError("answer_index out of range")

