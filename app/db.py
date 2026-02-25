import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple, Any, Dict


class KeyStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    # -------------------------
    # Connection
    # -------------------------
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row  
        return con

    def _ensure_columns(self, con: sqlite3.Connection, table: str, cols: dict) -> None:
        cur = con.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for col, ddl in cols.items():
            if col not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)

        with self._connect() as con:
            # -------------------------
            # API keys
            # -------------------------
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS user_keys (
                    user_id INTEGER PRIMARY KEY,
                    api_key TEXT NOT NULL
                )
                """
            )
            
            # -------------------------
            # Quiz attempts (per-question answers)
            # -------------------------
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    user_id INTEGER NOT NULL,
                    guild_id INTEGER,

                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,

                    choices_json TEXT,
                    user_answer TEXT,
                    correct_answer TEXT,

                    is_correct INTEGER NOT NULL CHECK(is_correct IN (0,1)),

                    explanation TEXT,
                    source TEXT,

                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            con.execute("CREATE INDEX IF NOT EXISTS idx_attempts_user_time ON quiz_attempts(user_id, created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_attempts_user_topic_time ON quiz_attempts(user_id, topic, created_at)")

            # -------------------------
            # Quiz scores (single source of truth)
            # -------------------------
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    guild_id INTEGER,
                    guild_name TEXT,

                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,

                    topic TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    total INTEGER NOT NULL,

                    duration_sec INTEGER DEFAULT 0,

                    avatar_url TEXT,
                    display_name TEXT,

                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # migrations (safe on existing DBs)
            self._ensure_columns(
                con,
                "quiz_scores",
                {
                    "guild_id": "INTEGER",
                    "guild_name": "TEXT",
                    "duration_sec": "INTEGER DEFAULT 0",
                    "avatar_url": "TEXT",
                    "display_name": "TEXT",
                    "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                },
            )

            con.execute("CREATE INDEX IF NOT EXISTS idx_scores_created ON quiz_scores(created_at)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_scores_guild ON quiz_scores(guild_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_scores_user ON quiz_scores(user_id)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_scores_topic ON quiz_scores(topic)")

            # -------------------------
            # Quiz seen (anti-repeat)
            # -------------------------
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_seen (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    sig TEXT NOT NULL,
                    starter3 TEXT,
                    question TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            con.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_quiz_seen_unique
                ON quiz_seen (guild_id, user_id, topic, sig)
                """
            )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_quiz_seen_recent
                ON quiz_seen (guild_id, user_id, topic, created_at)
                """
            )

            con.commit()
            
    def user_topic_breakdown(self, *, user_id: int, days: int = 30, guild_id: Optional[int] = None) -> List[Dict[str, Any]]:
                g_sql, g_args = self._guild_filter_sql(guild_id)
                t_sql, t_args = self._time_filter_sql(days)

                with self._connect() as con:
                    rows = con.execute(
                        f"""
                        SELECT
                        topic,
                        COUNT(*) AS quizzes,
                        COALESCE(SUM(score),0) AS correct,
                        COALESCE(SUM(total),0) AS total,
                        (COALESCE(SUM(score),0) * 1.0 / NULLIF(COALESCE(SUM(total),0),0)) AS accuracy,
                        COALESCE(SUM(score),0) AS points
                        FROM quiz_scores
                        WHERE user_id = ?
                        {g_sql}
                        {t_sql}
                        GROUP BY topic
                        HAVING total > 0
                        ORDER BY accuracy ASC, quizzes DESC
                        """,
                        (int(user_id), *g_args, *t_args),
                    ).fetchall()

                out: List[Dict[str, Any]] = []
                for r in rows:
                    out.append(
                        {
                            "topic": r["topic"],
                            "quizzes": int(r["quizzes"] or 0),
                            "correct": int(r["correct"] or 0),
                            "total": int(r["total"] or 0),
                            "accuracy": float(r["accuracy"] or 0.0),
                            "accuracy_pct": int(round((r["accuracy"] or 0.0) * 100)),
                            "points": int(r["points"] or 0),
                        }
                    )
                return out
    
    def add_quiz_attempt(
        self,
        *,
        user_id: int,
        guild_id: int | None,
        topic: str,
        question: str,
        is_correct: bool,
        user_answer: str | None = None,
        correct_answer: str | None = None,
        choices: list[str] | None = None,
        explanation: str | None = None,
        source: str = "discord",
    ) -> None:
        import json as _json

        choices_json = _json.dumps(choices, ensure_ascii=False) if choices else None

        with self._connect() as con:
            con.execute(
                """
                INSERT INTO quiz_attempts(
                user_id, guild_id, topic, question,
                choices_json, user_answer, correct_answer,
                is_correct, explanation, source
                )
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    int(user_id),
                    int(guild_id) if guild_id is not None else None,
                    str(topic or "unknown"),
                    str(question or ""),
                    choices_json,
                    (user_answer or None),
                    (correct_answer or None),
                    1 if is_correct else 0,
                    (explanation or None),
                    str(source or "discord"),
                ),
            )
            con.commit()
        
    def recent_wrong_attempts(
        self,
        *,
        user_id: int,
        days: int = 30,
        limit: int = 5,
        topic: str | None = None,
    ) -> list[dict]:
        t_sql, t_args = self._time_filter_sql(days)

        where_topic = "AND topic = ?" if topic else ""
        args = []
        if topic:
            args.append(str(topic))
        args.extend(t_args)

        with self._connect() as con:
            rows = con.execute(
                f"""
                SELECT topic, question, choices_json, user_answer, correct_answer, explanation, created_at
                FROM quiz_attempts
                WHERE user_id = ?
                AND is_correct = 0
                {where_topic}
                {t_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(user_id), *args, int(limit)),
            ).fetchall()

        out = []
        for r in rows or []:
            out.append(
                {
                    "topic": r["topic"],
                    "question": r["question"],
                    "choices_json": r["choices_json"],
                    "user_answer": r["user_answer"],
                    "correct_answer": r["correct_answer"],
                    "explanation": r["explanation"],
                    "when": str(r["created_at"]),
                }
            )
        return out


    # -------------------------
    # Helpers (filters)
    # -------------------------
    def _time_filter_sql(self, days: int) -> Tuple[str, Tuple[Any, ...]]:
        if int(days) == 0:
            return "", tuple()
        return " AND created_at >= datetime('now', ?) ", (f"-{int(days)} days",)

    def _guild_filter_sql(self, guild_id: Optional[int]) -> Tuple[str, Tuple[Any, ...]]:
        # None = GLOBAL (no filter, include everything)
        if guild_id is None:
            return "", tuple()

        # 0 = DM/Global-only bucket (legacy)
        if int(guild_id) == 0:
            return " AND (guild_id IS NULL OR guild_id = 0) ", tuple()

        # specific server
        return " AND guild_id = ? ", (int(guild_id),)

    # -------------------------
    # Guild helpers
    # -------------------------
    def list_known_guilds(self) -> List[Tuple[int, str]]:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT
                    guild_id,
                    COALESCE(MAX(NULLIF(TRIM(guild_name),'')), '') AS guild_name
                FROM quiz_scores
                WHERE guild_id IS NOT NULL AND guild_id != 0
                GROUP BY guild_id
                ORDER BY guild_name ASC, guild_id ASC
                """
            )
            rows = cur.fetchall() or []

        out: List[Tuple[int, str]] = []
        for r in rows:
            try:
                out.append((int(r["guild_id"]), str(r["guild_name"] or "")))
            except Exception:
                continue
        return out

    def get_guild_name(self, guild_id: int) -> Optional[str]:
        with self._connect() as con:
            cur = con.execute(
                """
                SELECT guild_name
                FROM quiz_scores
                WHERE guild_id = ?
                  AND guild_name IS NOT NULL
                  AND TRIM(guild_name) <> ''
                ORDER BY id DESC
                LIMIT 1
                """,
                (int(guild_id),),
            )
            row = cur.fetchone()
            return row["guild_name"] if row else None

    # -------------------------
    # Public profile / identity
    # -------------------------
    def get_user_public_profile(self, user_id: int) -> Dict[str, Any]:
        """
        Best-effort public profile from quiz_scores for a given user_id.
        Returns: {"display_name": str|None, "avatar_url": str|None}
        """
        with self._connect() as con:
            row = con.execute(
                """
                SELECT
                    COALESCE(
                        MAX(NULLIF(TRIM(display_name), '')),
                        MAX(NULLIF(TRIM(username), ''))
                    ) AS display_name,
                    MAX(NULLIF(TRIM(avatar_url), '')) AS avatar_url
                FROM quiz_scores
                WHERE user_id = ?
                """,
                (int(user_id),),
            ).fetchone()

        if not row:
            return {"display_name": None, "avatar_url": None}

        return {
            "display_name": row["display_name"] if row["display_name"] else None,
            "avatar_url": row["avatar_url"] if row["avatar_url"] else None,
        }

    def user_identity_from_scores(self, *, user_id: int) -> Dict[str, Optional[str]]:
        """
        Best-effort identity from quiz_scores (same source as leaderboard).
        Uses the most recent/non-null values via MAX() aggregation.
        """
        with self._connect() as con:
            row = con.execute(
                """
                SELECT
                COALESCE(MAX(display_name), MAX(username)) AS display_name,
                MAX(avatar_url) AS avatar_url
                FROM quiz_scores
                WHERE user_id = ?
                """,
                (int(user_id),),
            ).fetchone()

        if not row:
            return {"display_name": None, "avatar_url": None}

        return {
            "display_name": row["display_name"],
            "avatar_url": row["avatar_url"],
        }


    # -------------------------
    # API Keys
    # -------------------------
    def set_key(self, user_id: int, api_key: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO user_keys (user_id, api_key)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET api_key=excluded.api_key
                """,
                (int(user_id), api_key),
            )
            con.commit()

    def get_key(self, user_id: int) -> Optional[str]:
        with self._connect() as con:
            row = con.execute("SELECT api_key FROM user_keys WHERE user_id=?", (int(user_id),)).fetchone()
            return row["api_key"] if row else None

    def delete_key(self, user_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM user_keys WHERE user_id=?", (int(user_id),))
            con.commit()

    # -------------------------
    # Quiz Scores (write)
    # -------------------------
    def add_quiz_score(
        self,
        *,
        guild_id: Optional[int],
        guild_name: Optional[str],
        user_id: int,
        username: str,
        topic: str,
        score: int,
        total: int,
        duration_sec: int = 0,
        avatar_url: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO quiz_scores (
                    guild_id, guild_name,
                    user_id, username,
                    topic, score, total,
                    duration_sec,
                    avatar_url, display_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(guild_id) if guild_id is not None else None,
                    guild_name,
                    int(user_id),
                    username,
                    str(topic),
                    int(score),
                    int(total),
                    int(duration_sec),
                    avatar_url,
                    display_name,
                ),
            )
            con.commit()

    # -------------------------
    # Leaderboard aggregations
    # Returns rows:
    # (user_id, username, avatar_url, points, quizzes, accuracy)
    # -------------------------
    def top_users_agg(
        self,
        *,
        guild_id: Optional[int],
        topic: Optional[str] = None,
        limit: int = 10,
        days: int = 30,
        offset: int = 0,
    ) -> List[Tuple[Any, ...]]:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        t_sql, t_args = self._time_filter_sql(days)

        topic_sql = ""
        topic_args: Tuple[Any, ...] = tuple()
        if topic:
            topic_sql = " AND topic = ? "
            topic_args = (str(topic),)

        sql = f"""
            SELECT
                user_id,
                COALESCE(MAX(NULLIF(TRIM(display_name),'')), MAX(NULLIF(TRIM(username),''))) AS username,
                MAX(NULLIF(TRIM(avatar_url),'')) AS avatar_url,
                SUM(score) AS points,
                COUNT(*) AS quizzes,
                SUM(score)*1.0 / NULLIF(SUM(total), 0) AS accuracy
            FROM quiz_scores
            WHERE 1=1
            {topic_sql}
            {g_sql}
            {t_sql}
            GROUP BY user_id
            ORDER BY points DESC, accuracy DESC, quizzes DESC
            LIMIT ? OFFSET ?
        """
        args = (*topic_args, *g_args, *t_args, int(limit), int(offset))

        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()

        return [
            (r["user_id"], r["username"], r["avatar_url"], r["points"], r["quizzes"], r["accuracy"])
            for r in rows
        ]

    def count_users(self, *, guild_id: Optional[int], days: int = 30, topic: Optional[str] = None) -> int:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        t_sql, t_args = self._time_filter_sql(days)

        topic_sql = ""
        topic_args: Tuple[Any, ...] = tuple()
        if topic:
            topic_sql = " AND topic = ? "
            topic_args = (str(topic),)

        sql = f"""
            SELECT COUNT(DISTINCT user_id) AS n
            FROM quiz_scores
            WHERE 1=1
            {topic_sql}
            {g_sql}
            {t_sql}
        """
        args = (*topic_args, *g_args, *t_args)

        with self._connect() as con:
            row = con.execute(sql, args).fetchone()
            return int(row["n"] or 0)

    # compat: keep old names (optional)
    def top_users(self, *, guild_id: Optional[int], limit: int = 10, days: int = 30, offset: int = 0) -> List[Tuple[Any, ...]]:
        return self.top_users_agg(guild_id=guild_id, topic=None, limit=limit, days=days, offset=offset)

    def top_users_by_topic(
        self,
        *,
        guild_id: Optional[int],
        topic: str,
        limit: int = 10,
        days: int = 30,
        offset: int = 0,
    ) -> List[Tuple[Any, ...]]:
        return self.top_users_agg(guild_id=guild_id, topic=topic, limit=limit, days=days, offset=offset)

    def top_users_month(self, *, guild_id: Optional[int], limit: int = 10) -> List[Tuple[Any, ...]]:
        g_sql, g_args = self._guild_filter_sql(guild_id)

        sql = f"""
            SELECT
                user_id,
                COALESCE(MAX(NULLIF(TRIM(display_name),'')), MAX(NULLIF(TRIM(username),''))) AS username,
                MAX(NULLIF(TRIM(avatar_url),'')) AS avatar_url,
                SUM(score) AS points,
                COUNT(*) AS quizzes,
                SUM(score)*1.0 / NULLIF(SUM(total), 0) AS accuracy
            FROM quiz_scores
            WHERE created_at >= date('now','start of month')
              AND created_at <  date('now','start of month','+1 month')
            {g_sql}
            GROUP BY user_id
            ORDER BY points DESC, accuracy DESC, quizzes DESC
            LIMIT ?
        """
        args = (*g_args, int(limit))

        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()

        return [
            (r["user_id"], r["username"], r["avatar_url"], r["points"], r["quizzes"], r["accuracy"])
            for r in rows
        ]

    def season_winner(self, *, guild_id: Optional[int]) -> Optional[Tuple[Any, ...]]:
        rows = self.top_users_month(guild_id=guild_id, limit=1)
        if not rows:
            return None
        uid, uname, avatar_url, pts, quizzes, acc = rows[0]
        return (uid, uname, avatar_url, pts, acc, quizzes)

    # -------------------------
    # Topics
    # -------------------------
    def list_topics(self, *, guild_id: Optional[int], limit: int = 25) -> List[str]:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        sql = f"""
            SELECT topic, COUNT(*) AS n
            FROM quiz_scores
            WHERE 1=1
            {g_sql}
            GROUP BY topic
            ORDER BY n DESC, topic ASC
            LIMIT ?
        """
        args = (*g_args, int(limit))
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        return [row["topic"] for row in rows]

    # -------------------------
    # User stats
    # -------------------------


    def init_study_plans(db_path: str):
        con = sqlite3.connect(db_path)
        cur = con.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS study_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            start_date TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
        """)

        con.commit()
        con.close()

    def user_stats(self, *, user_id: int, guild_id: Optional[int], days: int = 30) -> Dict[str, Any]:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        t_sql, t_args = self._time_filter_sql(days)

        with self._connect() as con:
            row = con.execute(
                f"""
                SELECT COUNT(*) AS quizzes,
                       COALESCE(SUM(score),0) AS correct,
                       COALESCE(SUM(total),0) AS total
                FROM quiz_scores
                WHERE user_id = ?
                {g_sql}
                {t_sql}
                """,
                (int(user_id), *g_args, *t_args),
            ).fetchone()

            quizzes = int(row["quizzes"] or 0) if row else 0
            correct = int(row["correct"] or 0) if row else 0
            total = int(row["total"] or 0) if row else 0

            best = con.execute(
                f"""
                SELECT topic, SUM(score) AS pts
                FROM quiz_scores
                WHERE user_id = ?
                {g_sql}
                {t_sql}
                GROUP BY topic
                ORDER BY pts DESC
                LIMIT 1
                """,
                (int(user_id), *g_args, *t_args),
            ).fetchone()

        best_topic = best["topic"] if best else None
        accuracy = (correct / total) if total else 0.0
        return {"quizzes": quizzes, "correct": correct, "total": total, "accuracy": accuracy, "best_topic": best_topic}

    # Fallback “single source” (no guild filter) - utile in pages.py
    def user_stats_from_scores(self, *, user_id: int, days: int = 30) -> Dict[str, Any]:
        t_sql, t_args = self._time_filter_sql(days)

        with self._connect() as con:
            row = con.execute(
                f"""
                SELECT
                  COUNT(*) AS quizzes,
                  COALESCE(SUM(score),0) AS correct,
                  COALESCE(SUM(total),0) AS total,
                  SUM(score)*1.0 / NULLIF(SUM(total), 0) AS accuracy
                FROM quiz_scores
                WHERE user_id = ?
                {t_sql}
                """,
                (int(user_id), *t_args),
            ).fetchone()

            best = con.execute(
                f"""
                SELECT topic
                FROM quiz_scores
                WHERE user_id = ?
                {t_sql}
                GROUP BY topic
                ORDER BY SUM(score) DESC, COUNT(*) DESC
                LIMIT 1
                """,
                (int(user_id), *t_args),
            ).fetchone()

        return {
            "quizzes": int(row["quizzes"] or 0) if row else 0,
            "correct": int(row["correct"] or 0) if row else 0,
            "total": int(row["total"] or 0) if row else 0,
            "accuracy": float(row["accuracy"] or 0.0) if row and row["accuracy"] is not None else 0.0,
            "best_topic": best["topic"] if best else None,
        }

    def recent_user_runs(
        self, *, user_id: int, guild_id: Optional[int], limit: int = 10, days: int = 30
    ) -> List[Tuple[Any, ...]]:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        t_sql, t_args = self._time_filter_sql(days)

        sql = f"""
            SELECT topic, score, total, created_at
            FROM quiz_scores
            WHERE user_id = ?
            {g_sql}
            {t_sql}
            ORDER BY id DESC
            LIMIT ?
        """
        args = (int(user_id), *g_args, *t_args, int(limit))

        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        return [(r["topic"], r["score"], r["total"], r["created_at"]) for r in rows]

    def recent_user_runs_from_scores(self, *, user_id: int, days: int = 30, limit: int = 12) -> List[Tuple[Any, ...]]:
        t_sql, t_args = self._time_filter_sql(days)
        with self._connect() as con:
            rows = con.execute(
                f"""
                SELECT topic, score, total, created_at
                FROM quiz_scores
                WHERE user_id = ?
                {t_sql}
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (int(user_id), *t_args, int(limit)),
            ).fetchall()
        return [(r["topic"], r["score"], r["total"], r["created_at"]) for r in rows]

    def user_streak(self, *, user_id: int, guild_id: Optional[int]) -> Dict[str, int]:
        g_sql, g_args = self._guild_filter_sql(guild_id)

        with self._connect() as con:
            rows = con.execute(
                f"""
                SELECT DISTINCT date(created_at) AS d
                FROM quiz_scores
                WHERE user_id = ?
                {g_sql}
                ORDER BY d DESC
                """,
                (int(user_id), *g_args),
            ).fetchall()

        played: List[date] = []
        for r in rows:
            try:
                played.append(datetime.strptime(r["d"], "%Y-%m-%d").date())
            except Exception:
                continue

        played_set = set(played)
        days_played = len(played_set)

        today = date.today()
        streak = 0
        cur_day = today

        if cur_day not in played_set and (cur_day - timedelta(days=1)) in played_set:
            cur_day = cur_day - timedelta(days=1)

        while cur_day in played_set:
            streak += 1
            cur_day = cur_day - timedelta(days=1)

        return {"streak_days": streak, "days_played": days_played}

    def user_points_timeseries(self, *, user_id: int, guild_id: Optional[int], days: int = 30) -> List[Tuple[str, int]]:
        g_sql, g_args = self._guild_filter_sql(guild_id)
        t_sql, t_args = self._time_filter_sql(days)

        sql = f"""
        SELECT date(created_at) AS d, COALESCE(SUM(score),0) AS points
        FROM quiz_scores
        WHERE user_id = ?
        {g_sql}
        {t_sql}
        GROUP BY date(created_at)
        ORDER BY d ASC
        """
        with self._connect() as con:
            rows = con.execute(sql, (int(user_id), *g_args, *t_args)).fetchall()
        return [(r["d"], int(r["points"] or 0)) for r in rows]

    # -------------------------
    # Quiz Seen
    # -------------------------
    def add_quiz_seen(self, guild_id: int, user_id: int, topic: str, sig: str, starter3: str, question: str) -> None:
        topic_norm = (topic or "").strip().lower()
        with self._connect() as con:
            con.execute(
                """
                INSERT OR IGNORE INTO quiz_seen (guild_id, user_id, topic, sig, starter3, question)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(guild_id), int(user_id), topic_norm, sig, starter3 or "", question),
            )
            con.commit()

    def get_recent_quiz_seen(
        self,
        guild_id: int,
        user_id: int,
        topic: str,
        *,
        limit: int = 120,
        ttl_days: int = 30,
    ):
        topic_norm = (topic or "").strip().lower()
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT sig, starter3, question
                FROM quiz_seen
                WHERE guild_id=? AND user_id=? AND topic=?
                  AND created_at >= datetime('now', ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(guild_id), int(user_id), topic_norm, f"-{int(ttl_days)} days", int(limit)),
            ).fetchall()

        seen_sigs = set()
        seen_starters = set()
        avoid_questions: List[str] = []

        for r in rows:
            sig = r["sig"]
            starter3 = r["starter3"]
            question = r["question"]
            if sig:
                seen_sigs.add(sig)
            if starter3:
                seen_starters.add(starter3)
            if question:
                avoid_questions.append(question)

        return seen_sigs, seen_starters, avoid_questions

    def prune_quiz_seen(self, *, ttl_days: int = 60) -> int:
        with self._connect() as con:
            cur = con.execute("DELETE FROM quiz_seen WHERE created_at < datetime('now', ?)", (f"-{int(ttl_days)} days",))
            con.commit()
            return int(cur.rowcount or 0)

    def get_recent_quiz_avoid(
        self,
        guild_id: int,
        user_id: int,
        topic: str,
        *,
        limit: int = 120,
        ttl_days: int = 30,
    ):
        _, _, avoid_questions = self.get_recent_quiz_seen(guild_id, user_id, topic, limit=limit, ttl_days=ttl_days)
        return avoid_questions
