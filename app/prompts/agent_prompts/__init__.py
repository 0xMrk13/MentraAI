from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_agent_prompt(name: str) -> str:
    """
    Loads a prompt from app/agent_prompts/<name>.txt
    Example: load_agent_prompt("base") -> base.txt
    """
    safe = "".join(ch for ch in (name or "") if ch.isalnum() or ch in ("-", "_")).strip()
    if not safe:
        safe = "base"

    path = PROMPTS_DIR / f"{safe}.txt"
    if not path.exists():
        path = PROMPTS_DIR / "base.txt"

    return path.read_text(encoding="utf-8").strip()
