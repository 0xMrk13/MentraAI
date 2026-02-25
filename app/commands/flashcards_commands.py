import logging
import discord
from discord import app_commands

from app.utils.perms import clamp
from app.utils.text import clean_llm_text, topics_autocomplete
from app.utils.embeds import reply_embed, reply_error
from app.utils.loading import start_loading, stop_loading

from app.services.flashcards_gen import generate_flashcards
from app.views.flashcards_view import FlashcardsView

from app.models.cards import Flashcard
from app.constants import AI_FOOTER

log = logging.getLogger("Mentra")


async def run_flashcards_from_chat(
    *,
    channel: discord.abc.Messageable,
    user: discord.abc.User,
    topic: str,
    store,
    llm,
) -> None:
    api_key = store.get_key(user.id) or ""
    loading_msg = await channel.send(" 🗃️ Generating flashcards...")

    try:
        cards = await generate_flashcards(
            llm,
            api_key=api_key,
            topic=topic,
            n=10,
        )
    except Exception:
        log.exception("Chat flashcards failed")
        await loading_msg.edit(content="❌ Flashcards generation failed. Check logs.")
        return

    if not cards:
        await loading_msg.edit(content="❌ No flashcards returned. Try a more specific topic.")
        return

    cards_list: list[Flashcard] = []
    for c in cards:
        if isinstance(c, Flashcard):
            cards_list.append(c)
        elif isinstance(c, dict):
            q = str(c.get("q") or c.get("question") or "").strip()
            a = str(c.get("a") or c.get("answer") or "").strip()
            if q and a:
                cards_list.append(Flashcard(q=q, a=a))
        elif isinstance(c, (list, tuple)) and len(c) >= 2:
            q = str(c[0]).strip()
            a = str(c[1]).strip()
            if q and a:
                cards_list.append(Flashcard(q=q, a=a))

    if not cards_list:
        await loading_msg.edit(content="❌ Flashcards returned in an unknown format.")
        return
    
    view = FlashcardsView(
        owner_id=user.id,
        topic=clean_llm_text(topic)[:80],
        cards=cards_list,
    )

    try:
        intro = discord.Embed(
            title="🧠 Flashcards",
            description=(
                "• Reveal → verify recall\n"
                "• Next unlocks only after Reveal\n"
                "• Shuffle resets the session"
            ),
        )
        intro.add_field(name="Topic", value=f"• {clean_llm_text(topic) or '-'}", inline=False)
        intro.add_field(name="Cards", value=f"• {len(cards_list)}", inline=True)
        intro.add_field(name="Next move", value="• Run `/quiz` on the same topic", inline=True)
        intro.set_footer(text="Spaced repetition → then pressure test with /quiz\n" + AI_FOOTER)

        await loading_msg.edit(content=None, embed=intro)

        msg = await channel.send(embed=view.current_embed(), view=view)
        view.attach_message(msg)
    except Exception:
        log.exception("Chat flashcards send failed")
        try:
            await loading_msg.edit(content="❌ Failed to send flashcards UI.")
        except Exception:
            pass



def register_flashcards_commands(client: discord.Client, store, llm) -> None:
    @client.tree.command(
        name="flashcards",
        description="Train memory with interactive flashcards (reveal → recall → next).",
    )
    @app_commands.describe(
        topic="Pick a topic (suggestions available; custom topics also work)",
        count="How many cards (1–10)",
    )
    @app_commands.choices(
        count=[app_commands.Choice(name=str(i), value=i) for i in range(1, 11)]
    )
    async def flashcards(
        interaction: discord.Interaction,
        topic: str,
        count: app_commands.Choice[int],
    ):
        num_cards = clamp(int(count.value if count else 10), 1, 10)

        api_key = store.get_key(interaction.user.id) or ""
        await interaction.response.defer(thinking=True)
        _loading = await start_loading(interaction, "flashcards")

        try:
            cards = await generate_flashcards(
                llm,
                api_key=api_key,
                topic=topic,
                n=num_cards,
            )
        except Exception:
            log.exception("LLM /flashcards failed")
            await reply_error(interaction, "Flashcards generation failed. Check logs.", ephemeral=True)
            await stop_loading(_loading)
            return

        if not cards:
            await stop_loading(_loading)
            await reply_embed(
                interaction,
                title="Flashcards",
                description="No cards generated. Try a more specific topic.",
                footer=AI_FOOTER,
                ephemeral=True,
            )
            return

        # Coerce to Flashcard objects (in case generator returns dicts/tuples)
        cards_list: list[Flashcard] = []
        for c in cards:
            if isinstance(c, Flashcard):
                cards_list.append(c)
            elif isinstance(c, dict):
                q = str(c.get("q") or c.get("question") or "").strip()
                a = str(c.get("a") or c.get("answer") or "").strip()
                if q and a:
                    cards_list.append(Flashcard(q=q, a=a))
            elif isinstance(c, (list, tuple)) and len(c) >= 2:
                q = str(c[0]).strip()
                a = str(c[1]).strip()
                if q and a:
                    cards_list.append(Flashcard(q=q, a=a))

        if not cards_list:
            await stop_loading(_loading)
            await reply_error(
                interaction,
                "Flashcards returned in an unknown format.",
                hint="Check app/services/flashcards_gen.py output.",
                ephemeral=True,
            )
            return

        await stop_loading(_loading)

        view = FlashcardsView(
            owner_id=interaction.user.id,
            topic=clean_llm_text(topic)[:80],
            cards=cards_list,
        )

        await reply_embed(
            interaction,
            title="🧠 Flashcards",
            description=(
                "• Reveal → verify recall\n"
                "• Next unlocks only after Reveal\n"
                "• Shuffle resets the session"
            ),
            fields=[
                {"name": "Topic", "value": f"• {clean_llm_text(topic) or '-'}", "inline": False},
                {"name": "Cards", "value": f"• {len(cards_list)}", "inline": True},
                {"name": "Next move", "value": "• Run `/quiz` on the same topic", "inline": True},
            ],
            footer="Spaced repetition → then pressure test with /quiz\n" + AI_FOOTER,
            ephemeral=False,
        )

        msg = await interaction.followup.send(embed=view.current_embed(), view=view, ephemeral=False)
        view.attach_message(msg)

    @flashcards.autocomplete("topic")
    async def flashcards_topic_autocomplete(interaction: discord.Interaction, current: str):
        return await topics_autocomplete(current)
