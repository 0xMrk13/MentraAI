from typing import Dict, List
AI_FOOTER = "AI generated - Verify with official sources"
QUIZ_TOPICS: List[str] = [
    "Command Injection",
    "File Upload Vulnerabilities",
    "Authentication & Sessions",
    "Nmap Scanning",
    "Web Enumeration",
    "Linux Privilege Escalation",
    "Windows Privilege Escalation",
    "Active Directory Basics ",
    "Hashing & Salting",
    "Burp Suite ",
    "Wireshark ",
    "SOC Triage ",
    "Incident Response ",
    "MITRE ATT&CK Fundamentals",
]
BOT_VERSION = "12.0.0"
BOT_MODE = "Development"
RESOURCES: Dict[str, List[str]] = {
    "SQL Injection": [
        "PortSwigger Web Security Academy — SQL Injection (excellent labs)",
        "OWASP Cheat Sheet — SQL Injection Prevention",
        "TryHackMe — search rooms: 'SQL Injection', 'SQLi'",
    ],
    "XSS (Cross-Site Scripting)": [
        "PortSwigger Web Security Academy — XSS",
        "OWASP Cheat Sheet — XSS Prevention",
        "TryHackMe — search rooms: 'XSS'",
    ],
    "CSRF": [
        "PortSwigger Web Security Academy — CSRF",
        "OWASP Cheat Sheet — CSRF Prevention",
        "TryHackMe — web fundamentals rooms",
    ],
    "Nmap Scanning": [
        "Nmap Reference Guide (nmap.org/book)",
        "TryHackMe — Nmap room",
        "HTB Academy — Nmap fundamentals",
    ],
    "Active Directory Basics": [
        "Microsoft Learn — AD DS overview",
        "TryHackMe — Active Directory rooms",
        "HTB Academy — Active Directory modules",
    ],
    "Linux Privilege Escalation": [
        "GTFOBins",
        "HackTricks — Linux Privilege Escalation",
        "TryHackMe — Linux PrivEsc rooms",
    ],
    "Windows Privilege Escalation": [
        "LOLBAS",
        "HackTricks — Windows Privilege Escalation",
        "TryHackMe — Windows PrivEsc rooms",
    ],

}
MENTRA_SYSTEM = """
You are Mentra the in-app AI mentor.

Tone:
- friendly, natural, helpful.
- Not overly formal, not overly salesy.

Rules:
- Answer in English only.
- Keep it concise by default (2–5 lines).
- Ask at most ONE question if needed.

""".strip()

