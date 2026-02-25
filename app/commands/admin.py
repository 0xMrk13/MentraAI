# app/commands/admin.py
import logging
import discord
from discord import app_commands

from app.utils.perms import admin_only
from app.utils.embeds import reply_embed, reply_error

log = logging.getLogger("Mentra")


def register_admin_commands(client: discord.Client, store, llm) -> None:
    @client.tree.command(
        name="wipe_admin",
        description="ADMIN: Wipe + restore guild slash commands (fix duplicates).",
    )
    async def wipe_admin(interaction: discord.Interaction):
        if not admin_only(interaction):
            await reply_error(interaction, "Admin only.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        from config import GUILD_ID
        if not GUILD_ID:
            await reply_error(interaction, "GUILD_ID is 0 in .env.", ephemeral=True)
            return

        guild = discord.Object(id=GUILD_ID)

        try:
            # 1) Wipe ONLY guild commands
            client.tree.clear_commands(guild=guild)
            wiped = await client.tree.sync(guild=guild)  # applies the wipe
            log.info("wipe_admin: wiped guild commands, now=%d", len(wiped))

            # 2) Restore by copying globals -> guild and syncing again
            client.tree.copy_global_to(guild=guild)
            restored = await client.tree.sync(guild=guild)

            names = [c.name for c in restored]
            preview = "\n".join([f"• {n}" for n in names[:25]]) or "—"

            await reply_embed(
                interaction,
                title=" Wipe + Restore (Guild)",
                description=(
                    f"Wiped guild commands, then restored **{len(restored)}** commands "
                    f"on guild **{GUILD_ID}**."
                ),
                fields=[
                    {"name": "Commands restored", "value": preview, "inline": False},
                ],
                ephemeral=True,
            )

        except Exception:
            log.exception("wipe_admin failed")
            await reply_error(
                interaction,
                "wipe_admin failed. Check logs.",
                hint="If this keeps happening: restart the bot and run /wipe_admin again.",
                ephemeral=True,
            )
