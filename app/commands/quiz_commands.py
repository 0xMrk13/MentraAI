from __future__ import annotations

import logging

import discord
from discord import app_commands

from app.utils.perms import clamp
from app.utils.text import clean_llm_text, topics_autocomplete
from app.utils.embeds import reply_embed, reply_error
from app.utils.loading import start_loading, stop_loading

from app.services.quiz_gen import generate_quiz_questions
from app.views.quiz_view import QuizView
from app.constants import AI_FOOTER

log = logging.getLogger(__name__)


async def run_quiz_from_chat(
    *,
    client: discord.Client,
    channel: discord.abc.Messageable,
    user: discord.abc.User,
    guild_id: int,
    topic: str,
    num_questions: int,
    store,
    llm,
) -> None:
    num_q = clamp(int(num_questions), 1, 5)
    timed = True
    seconds = 60

    api_key = store.get_key(user.id) or ""

    loading_msg = await channel.send(":test_tube: Generating your quiz...")

    try:
        qs = await generate_quiz_questions(
            llm,
            api_key=api_key,
            topic=topic,
            n=num_q,
            store=store,
            guild_id=guild_id,
            user_id=user.id,
        )
    except Exception:
        log.exception("Chat /quiz failed")
        await loading_msg.edit(content="❌ Quiz generation failed. Check logs.")
        return

    if not qs:
        await loading_msg.edit(
            content="❌ No questions returned. Try a more specific topic."
        )
        return

    view = QuizView(
        store=store,
        owner_id=user.id,
        username=getattr(user, "name", "user"),
        topic=clean_llm_text(topic)[:80],
        questions=qs,
        timed=timed,
        seconds_per_question=seconds,
    )

    footer = "MentraAI • evidence → impact → remediation\n" + AI_FOOTER

    intro = discord.Embed(
        title="🧪 Quiz session",
        description=(
            "• Pick the best answer\n"
            "• Timed mode: **60s per question**\n"
            "• Review mistakes at the end"
        ),
    )
    intro.add_field(
        name="Topic", value=f"• {clean_llm_text(topic) or '-'}", inline=False
    )
    intro.add_field(name="Questions", value=f"• {len(qs)}", inline=True)
    intro.add_field(name="Timer", value="• 60s/question", inline=True)
    intro.set_footer(text=footer)

    try:
        await loading_msg.edit(content=None, embed=intro)
        msg = await channel.send(embed=view.build_embed(), view=view)
    except Exception:
        log.exception("Chat quiz send failed")
        return

    view.attach_message(msg)
    view.start_timer()


def register_quiz_commands(client: discord.Client, store, llm) -> None:
    @client.tree.command(
        name="quiz",
        description="Practice with timed offensive security quizzes (60s per question).",
    )
    @app_commands.describe(
        topic="Pick a topic (suggestions available; custom topics also work)",
        questions="How many questions (1–5)",
    )
    @app_commands.choices(
        questions=[
            app_commands.Choice(name="1", value=1),
            app_commands.Choice(name="2", value=2),
            app_commands.Choice(name="3", value=3),
            app_commands.Choice(name="4", value=4),
            app_commands.Choice(name="5", value=5),
        ]
    )
    async def quiz(
        interaction: discord.Interaction,
        topic: str,
        questions: app_commands.Choice[int] | None = None,
    ) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(thinking=True)
        except (discord.NotFound, discord.InteractionResponded):
            return

        num_q = clamp(int(questions.value if questions else 5), 1, 5)
        timed = True
        seconds = 60

        api_key = store.get_key(interaction.user.id) or ""

        loading_msg = await start_loading(interaction, "quiz")

        try:
            qs = await generate_quiz_questions(
                llm,
                api_key=api_key,
                topic=topic,
                n=num_q,
                store=store,
                guild_id=interaction.guild_id or 0,
                user_id=interaction.user.id,
            )
        except Exception:
            log.exception("LLM /quiz failed")
            await stop_loading(loading_msg)
            await reply_error(
                interaction, "Quiz generation failed. Check logs.", ephemeral=True
            )
            return

        if not qs:
            await stop_loading(loading_msg)
            await reply_error(
                interaction,
                "No questions returned by the model.",
                hint="Try a more specific topic (e.g., 'XSS reflected vs stored') or try again.",
                ephemeral=True,
            )
            return

        await stop_loading(loading_msg)

        view = QuizView(
            store=store,
            owner_id=interaction.user.id,
            username=getattr(interaction.user, "name", "user"),
            topic=clean_llm_text(topic)[:80],
            questions=qs,
            timed=timed,
            seconds_per_question=seconds,
        )

        footer = "Mentra • evidence → impact → remediation\n" + AI_FOOTER

        try:
            await reply_embed(
                interaction,
                title="🧪 Quiz session",
                description=(
                    "• Pick the best answer\n"
                    "• Timed mode: **60s per question**\n"
                    "• Review mistakes at the end"
                ),
                fields=[
                    {
                        "name": "Topic",
                        "value": f"• {clean_llm_text(topic) or '-'}",
                        "inline": False,
                    },
                    {"name": "Questions", "value": f"• {len(qs)}", "inline": True},
                    {"name": "Timer", "value": "• 60s/question", "inline": True},
                ],
                footer=footer,
                ephemeral=False,
            )
        except discord.NotFound:
            return

        try:
            msg = await interaction.followup.send(
                embed=view.build_embed(), view=view, ephemeral=False
            )
        except discord.NotFound:
            return

        view.attach_message(msg)
        view.start_timer()

    @quiz.autocomplete("topic")
    async def quiz_topic_autocomplete(interaction: discord.Interaction, current: str):
        return await topics_autocomplete(current)
