import logging
from typing import Optional, Tuple, Any

import discord
from discord import app_commands

log = logging.getLogger("Mentra")


def _ascii_bar(pct: int, width: int = 10) -> str:
    try:
        pct = int(pct)
    except Exception:
        pct = 0
    pct = max(0, min(100, pct))

    filled = int(round((pct / 100) * width))
    filled = max(0, min(width, filled))
    return "[" + ("#" * filled) + ("." * (width - filled)) + "]"


def _lb_parse_row(row: Tuple[Any, ...]) -> Tuple[int, str, Optional[str], int, int, float]:
    """
    Normalizza una row leaderboard in:
    (user_id, username, avatar_url, points, quizzes, acc_float_0_1)

    Supporta:
      - (user_id, username, points, quizzes, acc)
      - (user_id, username, avatar_url, points, quizzes, acc)
    """
    if not row:
        return 0, "unknown", None, 0, 0, 0.0

    if len(row) >= 6:
        user_id, username, avatar_url, points, quizzes, acc = row[:6]
    else:
        user_id, username, points, quizzes, acc = row[:5]
        avatar_url = None

    try:
        user_id = int(user_id)
    except Exception:
        user_id = 0

    username = str(username or "unknown")
    avatar_url = str(avatar_url) if avatar_url else None

    try:
        points = int(points or 0)
    except Exception:
        points = 0

    try:
        quizzes = int(quizzes or 0)
    except Exception:
        quizzes = 0

    try:
        acc = float(acc or 0.0)
    except Exception:
        acc = 0.0

    return user_id, username, avatar_url, points, quizzes, acc


def _rank_prefix(i: int) -> str:
    if i == 1:
        return "🥇"
    if i == 2:
        return "🥈"
    if i == 3:
        return "🥉"
    return f"`#{i}`"


def register_stats_commands(client: discord.Client, store, llm) -> None:

    # -----------------------------
    # /rank
    # -----------------------------
    @client.tree.command(name="rank", description="See the top performers (points + accuracy).")
    @app_commands.describe(
        topic="Filter by topic (e.g. xss, sqli, privesc). Leave empty for overall.",
        alltime="If true, uses all-time stats instead of last 30 days.",
        season="If true, uses this month's leaderboard (season).",
    )
    async def rank(
        interaction: discord.Interaction,
        topic: Optional[str] = None,
        alltime: bool = False,
        season: bool = False,
    ):
        # GLOBAL leaderboard (same as web)
        guild_id = None

        # normalize topic
        topic_norm = (topic or "").strip()
        topic_norm = topic_norm or None

        if season and not alltime and not topic_norm:
            rows = store.top_users_month(guild_id=guild_id, limit=10)
            title = "🏆 Leaderboard — Season (This month)"
            timeframe = "This month"
        else:
            days = 0 if alltime else 30
            timeframe = "All-time" if alltime else "Last 30 days"
            if topic_norm:
                rows = store.top_users_by_topic(guild_id=guild_id, topic=topic_norm, limit=10, days=days)
                title = f"🏆 Leaderboard — {topic_norm.lower()}"
            else:
                rows = store.top_users(guild_id=guild_id, limit=10, days=days)
                title = "🏆 Leaderboard"

        if not rows:
            await interaction.response.send_message("No quiz data yet.", ephemeral=True)
            return

        scope = "Global" if guild_id is None else (interaction.guild.name if interaction.guild else "Server")

        lines = []
        for i, row in enumerate(rows, start=1):
            _uid, username, _avatar, points, quizzes, acc = _lb_parse_row(row)
            acc_pct = int((acc or 0) * 100)
            bar = _ascii_bar(acc_pct, width=10)

            prefix = _rank_prefix(i)
            lines.append(
                f"{prefix} **{username}**\n"
                f"└ **{points} pts** • 🎯 {acc_pct}% `{bar}` • 🧪 {quizzes} quiz"
            )

        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
        )
        embed.set_footer(text=f"{scope} • {timeframe}")
        await interaction.response.send_message(embed=embed)

    @rank.autocomplete("topic")
    async def topic_autocomplete(interaction: discord.Interaction, current: str):
        # Coerente col leaderboard globale: usa guild_id=None
        try:
            topics = store.list_topics(guild_id=None, limit=25)
        except Exception:
            topics = []
        current_l = (current or "").lower().strip()
        hits = [t for t in topics if current_l in (t or "").lower()]
        return [app_commands.Choice(name=t, value=t) for t in hits[:25]]

    # -----------------------------
    # /rankme
    # -----------------------------
    @client.tree.command(name="rankme", description="See your current position in the leaderboard.")
    @app_commands.describe(alltime="If true, uses all-time stats instead of last 30 days.")
    async def rankme(interaction: discord.Interaction, alltime: bool = False):
        guild_id = None
        days = 0 if alltime else 30
        timeframe = "All-time" if alltime else "Last 30 days"

        r = store.user_rank(guild_id=guild_id, user_id=interaction.user.id, days=days)
        if not r:
            await interaction.response.send_message("No data for you yet. Play a quiz first 🙂", ephemeral=True)
            return

        # atteso: (pos, points, acc, quizzes)
        pos, points, acc, quizzes = r
        try:
            pos = int(pos or 0)
        except Exception:
            pos = 0
        try:
            points = int(points or 0)
        except Exception:
            points = 0
        try:
            quizzes = int(quizzes or 0)
        except Exception:
            quizzes = 0
        try:
            acc = float(acc or 0.0)
        except Exception:
            acc = 0.0

        acc_pct = int(acc * 100)
        bar = _ascii_bar(acc_pct, width=10)

        gap = store.user_gap_to_top(guild_id=guild_id, user_id=interaction.user.id, days=days)
        gap_txt = f"{gap} pts behind #1" if gap and gap > 0 else "You are #1 🥇"

        scope = "Global" if guild_id is None else (interaction.guild.name if interaction.guild else "Server")

        embed = discord.Embed(
            title=f"📍 Rank — {interaction.user.name}",
            description=(
                f"**Position:** #{pos}\n"
                f"**Score:** **{points} pts** • 🎯 {acc_pct}% `{bar}` • 🧪 {quizzes} quiz\n"
                f"**Gap:** {gap_txt}\n"
                f"**Range:** {timeframe}"
            ),
        )
        embed.set_footer(text=scope)
        await interaction.response.send_message(embed=embed)

    # -----------------------------
    # /rank_accuracy
    # -----------------------------
    @client.tree.command(name="rank_accuracy", description="Top accuracy (fair leaderboard with min games).")
    @app_commands.describe(
        alltime="If true, uses all-time stats instead of last 30 days.",
        min_games="Minimum quizzes played to appear (default 10).",
    )
    async def rank_accuracy(
        interaction: discord.Interaction,
        alltime: bool = False,
        min_games: int = 10,
    ):
        guild_id = None
        days = 0 if alltime else 30
        timeframe = "All-time" if alltime else "Last 30 days"

        if min_games < 1:
            min_games = 1
        if min_games > 200:
            min_games = 200

        rows = store.top_accuracy(guild_id=guild_id, limit=10, days=days, min_games=min_games)
        if not rows:
            await interaction.response.send_message("Not enough data yet (try lowering min_games).", ephemeral=True)
            return

        scope = "Global" if guild_id is None else (interaction.guild.name if interaction.guild else "Server")

        lines = []
        for i, row in enumerate(rows, start=1):
            # atteso store.top_accuracy:
            # (user_id, username, acc_pct, quizzes, points) [+ avatar_url opzionale]
            if len(row) >= 6:
                _user_id, username, _avatar_url, acc_pct, quizzes, points = row[:6]
            else:
                _user_id, username, acc_pct, quizzes, points = row[:5]

            try:
                acc_pct = int(acc_pct or 0)
            except Exception:
                acc_pct = 0
            acc_pct = max(0, min(100, acc_pct))

            try:
                quizzes = int(quizzes or 0)
            except Exception:
                quizzes = 0

            try:
                points = int(points or 0)
            except Exception:
                points = 0

            bar = _ascii_bar(acc_pct, width=10)
            prefix = _rank_prefix(i)

            lines.append(
                f"{prefix} **{username}**\n"
                f"└ 🎯 **{acc_pct}%** `{bar}` • 🧪 {quizzes} quiz • **{points} pts**"
            )

        embed = discord.Embed(
            title="🎯 Accuracy Leaderboard",
            description="\n".join(lines),
        )
        embed.set_footer(text=f"{scope} • {timeframe} • min {min_games} quiz")
        await interaction.response.send_message(embed=embed)

    # -----------------------------
    # /season_winner
    # -----------------------------
    @client.tree.command(name="season_winner", description="Show this month's #1 player (points).")
    async def season_winner(interaction: discord.Interaction):
        guild_id = None
        row = store.season_winner(guild_id=guild_id)

        if not row:
            await interaction.response.send_message("No season data yet.", ephemeral=True)
            return

        # dal tuo KeyStore: return (uid, uname, avatar_url, pts, acc, quizzes)
        if len(row) >= 6:
            _user_id, username, _avatar_url, points, acc, quizzes = row[:6]
        else:
            # fallback (se cambi in futuro)
            _user_id, username, points, acc, quizzes = row[:5]

        try:
            points = int(points or 0)
        except Exception:
            points = 0
        try:
            quizzes = int(quizzes or 0)
        except Exception:
            quizzes = 0
        try:
            acc = float(acc or 0.0)
        except Exception:
            acc = 0.0

        acc_pct = int(acc * 100)
        bar = _ascii_bar(acc_pct, width=10)

        embed = discord.Embed(
            title="🏅 Season Winner (This month)",
            description=(
                f"🥇 **{username}**\n"
                f"**{points} pts** • 🎯 {acc_pct}% `{bar}` • 🧪 {quizzes} quiz"
            ),
        )
        await interaction.response.send_message(embed=embed)

    # -----------------------------
    # /stats
    # -----------------------------
    @client.tree.command(name="stats", description="View your stats + recent quiz runs.")
    @app_commands.describe(alltime="If true, uses all-time stats instead of last 30 days.")
    async def stats(interaction: discord.Interaction, alltime: bool = False):
        guild_id = None
        days = 0 if alltime else 30
        timeframe = "All-time" if alltime else "Last 30 days"

        s = store.user_stats(user_id=interaction.user.id, guild_id=guild_id, days=days)

        try:
            streak = store.user_streak(user_id=interaction.user.id, guild_id=guild_id) or {}
        except Exception:
            streak = {}

        quizzes = int(s.get("quizzes", 0) or 0)
        correct = int(s.get("correct", 0) or 0)
        total = int(s.get("total", 0) or 0)

        acc_pct = int((s.get("accuracy") or 0) * 100) if total else 0
        best = s.get("best_topic") or "—"

        # FIX: il tuo store ritorna "streak_days", non "current_streak"
        current_streak = int(streak.get("streak_days", 0) or 0)
        days_played = int(streak.get("days_played", 0) or 0)

        embed = discord.Embed(
            title=f"📊 Stats — {interaction.user.name}",
            description=(
                f"🧪 Quizzes taken: **{quizzes}**\n"
                f"✅ Correct answers: **{correct}/{total}**\n"
                f"🎯 Accuracy: **{acc_pct}%**\n"
                f"⭐ Best topic: **{best}**\n"
                f"🔥 Streak: **{current_streak} days**\n"
                f"🗓️ Days played: **{days_played}**\n"
                f"⏱️ Range: **{timeframe}**"
            ),
        )

        runs = store.recent_user_runs(user_id=interaction.user.id, guild_id=guild_id, limit=5, days=days)
        if runs:
            lines = []
            for topic, score, tot, created in runs:
                lines.append(f"• {topic} — {score}/{tot} ({created})")

            embed.add_field(
                name="🕘 Recent runs",
                value="\n".join(lines),
                inline=False,
            )

        await interaction.response.send_message(embed=embed)