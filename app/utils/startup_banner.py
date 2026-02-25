import platform
import sys
import logging

log = logging.getLogger("MentraAI")


def startup_banner(
    *,
    provider: str,
    model: str,
    api: str,
    commands: int,
    version: str,
    mode: str,
) -> None:
    python_ver = sys.version.split()[0]
    os_name = platform.system()

    rows = [
        ("CORE", f"MentraAI v{version}"),
        ("ENV", mode),
        ("RUNTIME", f"Python {python_ver}"),
        ("HOST", os_name),
        ("AI-ENGINE", f"{model}"),
        ("LINK", api),
        ("MODULES", str(commands)),
        ("STATUS", "OPERATIONAL"),
    ]

    width = 44
    line = "─" * width

    log.info(line)
    log.info(" >o< MentraAI is online")
    log.info("")

    label_width = max(len(k) for k, _ in rows)

    for k, v in rows:
        log.info(f"{k.ljust(label_width)} : {v}")

    log.info(line)
