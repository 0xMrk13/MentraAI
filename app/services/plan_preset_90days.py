import re
from typing import Any, Dict, List

_PRESET_90DAYS_ALIASES = {
    "90days",
    "90 days",
    "90day",
    "90-day",
    "90 days of cybersecurity",
    "90daysofcybersecurity",
}

_90DAYS_SEGMENTS: List[Dict[str, Any]] = [
    {
        "start": 1,
        "end": 7,
        "label": "Network+ Concepts",
        "resources": [
            "Professor Messer N10-009 Playlist (YouTube): https://www.youtube.com/watch?v=k7IOn3TiUc8&list=PLG49S3nxzAnl_tQe3kvnmeMid0mjF8Le8",
        ],
    },
    {
        "start": 8,
        "end": 14,
        "label": "Security+ Concepts",
        "resources": [
            "Professor Messer SY0-701 Playlist (YouTube): https://www.youtube.com/watch?v=KiEptGbnEBc&list=PLG49S3nxzAnl4QDVqK-hOnoqcSKEIDDuv",
            "Pete Zerger SY0-701 Playlist (YouTube): https://www.youtube.com/watch?v=1E7pI7PB4KI&list=PL7XJSuT7Dq_UDJgYoQGIW9viwM5hc4C7n",
        ],
    },
    {
        "start": 15,
        "end": 28,
        "label": "Linux Tutorials",
        "resources": [
            "Linux Journey: https://linuxjourney.com/",
            "Cisco NetAcad Linux Unhatched: https://www.netacad.com/courses/linux-unhatched",
            "LabEx Linux Labs: https://labex.io/free-labs/linux",
        ],
    },
    {
        "start": 29,
        "end": 42,
        "label": "Python for Security",
        "resources": [
            "Codecademy Learn Python: https://codecademy.com/learn/learn-python",
            "Real Python: https://realpython.com/",
            "HackerRank Python: https://www.hackerrank.com/domains/python",
            "Learn Python the Hard Way: https://learnpythonthehardway.org",
            "TCM Python Course (YouTube): https://www.youtube.com/watch?v=egg-GoT5iVk&ab_channel=TheCyberMentor",
        ],
    },
    {
        "start": 43,
        "end": 56,
        "label": "Traffic Analysis (Wireshark / tcpdump / Suricata)",
        "resources": [
            "Wireshark Educational Content: https://www.wireshark.org/#educationalContent",
            "guru99 Wireshark Tutorial: https://guru99.com/wireshark-tutorial.html",
            "Daniel Miessler tcpdump tutorial: https://danielmiessler.com/study/tcpdump/",
            "Suricata on pfSense guide: https://doc.pfsense.org/index.php/Suricata",
        ],
    },
    {
        "start": 57,
        "end": 63,
        "label": "Git Basics",
        "resources": [
            "Codecademy Git for Beginners: https://codecademy.com/learn/learn-git",
            "Git Immersion: http://gitimmersion.com",
            "Try Git: https://try.github.io",
            "Learn Git Branching: https://learngitbranching.js.org/",
        ],
    },
    {
        "start": 64,
        "end": 70,
        "label": "ELK Stack (SIEM / Log Analysis)",
        "resources": [
            "Logz.io ELK tutorial: https://logz.io/learn/complete-elk-stack-tutorial/",
            "Elastic Learn (Elastic Stack): https://elastic.co/learn/elastic-stack",
        ],
    },
    {
        "start": 71,
        "end": 77,
        "label": "Cloud Platforms (GCP / AWS / Azure)",
        "resources": [
            "GCP Getting Started: https://cloud.google.com/getting-started/",
            "AWS Getting Started: https://aws.amazon.com/getting-started/",
            "Azure Fundamentals (Microsoft Learn): https://learn.microsoft.com/en-us/training/azure/",
        ],
    },
    {
        "start": 78,
        "end": 84,
        "label": "Review + Mini Projects (Bridge Week)",
        "resources": [
            "Pick 1 mini-project: home lab notes, 2 short writeups, or review weak areas from previous weeks.",
            "Optional: create a tiny portfolio / notes system (Notion/GitHub).",
        ],
    },
    {
        "start": 85,
        "end": 90,
        "label": "Hacking (Ethical Hacking Practice)",
        "resources": [
            "Hack The Box: https://hackthebox.com",
            "VulnHub: https://vulnhub.com",
            "TCM Ethical Hacking Part 1 (YouTube): https://www.youtube.com/watch?v=3FNYvj2U0HM&ab_channel=TheCyberMentor",
            "TCM Ethical Hacking Part 2 (YouTube): https://www.youtube.com/watch?v=sH4JCwjybGs&ab_channel=TheCyberMentor",
        ],
    },
    {
        "start": 91,
        "end": 92,
        "label": "One Page Resume",
        "resources": [
            "BowTiedCyber resume guide: https://bowtiedcyber.substack.com/p/killer-cyber-resume-part-ii",
            "Indeed cybersecurity resume advice: https://www.indeed.com/career-advice/resumes-cover-letters/cybersecurity-resume",
        ],
    },
    {
        "start": 93,
        "end": 95,
        "label": "Where and How to Apply",
        "resources": [
            "Indeed: https://indeed.com",
            "LinkedIn: https://linkedin.com",
        ],
    },
]


def is_90days_preset(topic: str) -> bool:
    t = (topic or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t in _PRESET_90DAYS_ALIASES


def segment_for_day(day: int) -> Dict[str, Any]:
    for seg in _90DAYS_SEGMENTS:
        if seg["start"] <= day <= seg["end"]:
            return seg
    return {"start": day, "end": day, "label": "General", "resources": []}


def resources_block(resources: List[str]) -> str:
    if not resources:
        return ""
    return "\n".join([f"- {r}" for r in resources[:5]]).strip()


def week_number_for_day(day: int) -> int:
    return ((day - 1) // 7) + 1
