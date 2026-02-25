import re
from typing import Literal

from app.utils.text import (
    clean_llm_text,
    strip_code_fences,
    cutoff_at_markers,
    normalize_newlines,
    limit,
)

AskMode = Literal["chat", "explain", "playbook"]

ASK_SOFT_CAP = 2600
ASK_DESCRIPTION_CAP = 3600
MAX_BULLET_LINES = 10

_MENTRA_HEADINGS_RE = re.compile(
    r"(?im)^\s*(TL;DR|Operator Notes|Recon Checklist|Impact|Mitigations|Reporting Notes|Next Actions)\s*:\s*$"
)


def decide_mode(question: str) -> AskMode:
    ql = (question or "").strip().lower()
    if not _is_cyber_related(ql):
        return "chat"
    if _wants_hands_on_playbook(ql):
        return "playbook"
    return "explain"


def build_system_prompt(mode: AskMode, question: str) -> str:
    if mode == "chat":
        return (
            "You are MentraAI.\n"
            "ENGLISH ONLY.\n"
            "The user is asking a NON-cybersecurity question.\n"
            "Reply naturally in 1-2 short sentences.\n"
            "No headings. No templates. No disclaimers.\n"
        )

    if mode == "explain":
        return (
            "You are MentraAI, a cybersecurity study tutor.\n"
            "ENGLISH ONLY.\n\n"
            "OUTPUT GOAL:\n"
            "- Write a compact but helpful explanation (10-16 lines).\n"
            "- Avoid one-liners.\n\n"
            "STRUCTURE (use this order when applicable):\n"
            "1) One-sentence definition or summary.\n"
            "2) 3-5 key points as '-' bullets (max 6 bullets).\n"
            "3) If relevant, add 1 short example or common use case (1 sentence).\n\n"
            "STYLE:\n"
            "- Use short sentences.\n"
            "- Use '-' bullets only (no nested bullets).\n"
            "- NO backticks and NO code blocks.\n"
            "- No JSON.\n"
            "- Do not write 'Rules' or repeat instructions.\n"
            "- Stay safe and legal: labs/authorized contexts only.\n"
        )

    # playbook
    return (
        "You are MentraAI, an Offensive Security study assistant.\n"
        "ENGLISH ONLY.\n\n"
        "Use EXACT headings (each on its own line, with a colon):\n"
        "TL;DR:\n"
        "Operator Notes:\n"
        "Recon Checklist:\n"
        "Impact:\n"
        "Mitigations:\n"
        "Reporting Notes:\n"
        "Next Actions:\n\n"
        "STYLE:\n"
        "- Keep each section SHORT (2-4 bullets max).\n"
        "- Use '-' bullets only. NO nested bullets.\n"
        "- NO backticks and NO code blocks.\n"
        "- No JSON.\n\n"
        "SAFETY:\n"
        "- Assume authorized labs only.\n"
        "- Do NOT provide steps to hack real targets.\n"
        "- If asked for illegal/dangerous steps, redirect to legal/defensive alternatives.\n"
        "- Do not write 'Rules' or repeat instructions.\n"
    )


def looks_like_playbook(text: str) -> bool:
    return bool(_MENTRA_HEADINGS_RE.search(text or ""))


def normalize_playbook_headings(text: str) -> str:
    t = normalize_newlines(text).strip()
    t = re.sub(r"(?im)^\s*TL;DR\s*:\s*$", "🧷 **TL;DR**", t)
    t = re.sub(r"(?im)^\s*Operator Notes\s*:\s*$", "📝 **Operator Notes**", t)
    t = re.sub(r"(?im)^\s*Recon Checklist\s*:\s*$", "🛰️ **Recon Checklist**", t)
    t = re.sub(r"(?im)^\s*Impact\s*:\s*$", "💥 **Impact**", t)
    t = re.sub(r"(?im)^\s*Mitigations\s*:\s*$", "🛡️ **Mitigations**", t)
    t = re.sub(r"(?im)^\s*Reporting Notes\s*:\s*$", "📄 **Reporting Notes**", t)
    t = re.sub(r"(?im)^\s*Next Actions\s*:\s*$", "⏭️ **Next Actions**", t)
    return t.strip()


def postprocess_answer(raw: str) -> str:
    text = clean_llm_text(raw or "").strip()
    text = strip_code_fences(text)
    text = cutoff_at_markers(text)
    text = normalize_newlines(text)

    # remove inline backticks (no code pills)
    text = text.replace("`", "")

    # normalize bullets and clamp bullet spam
    lines_in = text.splitlines()
    out = []
    bullet_lines = 0

    for ln in lines_in:
        s = ln.replace("\t", " ").strip()

        # normalize bullet prefixes
        s = re.sub(r"^[•●∙·]\s*", "- ", s)
        s = re.sub(r"^[–—]\s*", "- ", s)
        s = re.sub(r"^\d+\)\s+", "- ", s)
        s = re.sub(r"^\d+\.\s+", "- ", s)

        if not s:
            out.append("")
            continue

        if s.startswith("- "):
            bullet_lines += 1
            if bullet_lines > MAX_BULLET_LINES:
                continue

        out.append(s)

    text = normalize_newlines("\n".join(out)).strip()

    # soft cap (trim nicely)
    if len(text) > ASK_SOFT_CAP:
        cut = text[:ASK_SOFT_CAP].rstrip()
        nl = cut.rfind("\n")
        if nl > 700:
            cut = cut[:nl].rstrip()
        text = cut + "\n\n…(too long) Ask a narrower question."

    return text


def render_for_description(answer: str) -> str:
    return limit((answer or "").strip(), ASK_DESCRIPTION_CAP)


# -----------------------------
# Detectors
# -----------------------------
def _is_cyber_related(ql: str) -> bool:
    keywords = [
        "tcp",
        "udp",
        "ip",
        "dns",
        "dhcp",
        "http",
        "https",
        "tls",
        "ssl",
        "ssh",
        "rdp",
        "vpn",
        "firewall",
        "proxy",
        "waf",
        "port",
        "packet",
        "wireshark",
        "tcpdump",
        "suricata",
        "auth",
        "authentication",
        "authorization",
        "oauth",
        "saml",
        "jwt",
        "encryption",
        "certificate",
        "pki",
        "xss",
        "sqli",
        "csrf",
        "rce",
        "lfi",
        "rfi",
        "malware",
        "ransomware",
        "phishing",
        "siem",
        "elk",
        "edr",
        "ids",
        "ips",
        "nmap",
        "burp",
        "kali",
        "ctf",
        "tryhackme",
        "hackthebox",
        "pentest",
        "penetration",
        "vulnerability",
        "exploit",
        "oscp",
        "security+",
        "network+",
        "recon",
        "enumeration",
        "server",
        "protocol",
        "ports",
    ]
    return any(k in ql for k in keywords)


def _wants_hands_on_playbook(ql: str) -> bool:
    triggers = [
        "how do i",
        "step by step",
        "steps",
        "checklist",
        "troubleshoot",
        "debug",
        "can't connect",
        "cannot connect",
        "connection refused",
        "timeout",
        "timed out",
        "error",
        "failed",
        "investigate",
        "incident",
        "triage",
        "analyze",
        "scan",
        "enumerate",
        "recon",
        "payload",
        "poc",
        "ctf",
        "lab",
        "tryhackme",
        "hackthebox",
    ]
    return any(t in ql for t in triggers)
