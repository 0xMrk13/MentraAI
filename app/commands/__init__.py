from .admin import register_admin_commands
from .study import register_study_commands
from .stats_commands import register_stats_commands
from .quiz_commands import register_quiz_commands
from .flashcards_commands import register_flashcards_commands

__all__ = [
    "register_admin_commands",
    "register_study_commands",
    "register_stats_commands",
    "register_quiz_commands",
    "register_flashcards_commands",
]
