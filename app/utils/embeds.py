from typing import Any, Dict, List, Optional
import discord


def _chunk_text(text: str, limit: int = 900) -> List[str]:
    text = (text or "").strip()
    if not text:
        return ["-"]
    chunks: List[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def make_embed(
    title: str,
    description: str = "",
    *,
    footer: str = "",
    fields: Optional[List[Dict[str, Any]]] = None,
) -> discord.Embed:
    e = discord.Embed(
        title=title[:256],
        description=(description[:4096] if description else ""),
        color=discord.Color.dark_grey(),
        timestamp=discord.utils.utcnow(),
    )

    if fields:
        for f in fields:
            name = str(f.get("name", ""))[:256]
            value = str(f.get("value", "-"))
            inline = bool(f.get("inline", False))

            parts = _chunk_text(value, 1024)
            e.add_field(name=name, value=parts[0], inline=inline)
            for i, p in enumerate(parts[1:], start=2):
                e.add_field(name=f"{name[:240]} (cont. {i})", value=p, inline=inline)

            if len(e.fields) >= 25:
                break

    if footer:
        e.set_footer(text=footer[:2048])
    return e


async def reply_embed(
    interaction: discord.Interaction,
    *,
    title: str,
    description: str = "",
    footer: str = "",
    fields: Optional[List[Dict[str, Any]]] = None,
    ephemeral: bool = False,
) -> None:
    e = make_embed(title=title, description=description, footer=footer, fields=fields)
    if interaction.response.is_done():
        await interaction.followup.send(embed=e, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(embed=e, ephemeral=ephemeral)


async def reply_error(
    interaction: discord.Interaction,
    message: str,
    *,
    hint: str = "",
    ephemeral: bool = True,
) -> None:
    fields = [{"name": "Error", "value": message, "inline": False}]
    if hint:
        fields.append({"name": "Hint", "value": hint, "inline": False})
    await reply_embed(
        interaction,
        title="⚠️ Something went wrong",
        description="Please try again.",
        fields=fields,
        ephemeral=ephemeral,
        footer="If this keeps happening, check your LLM backend and logs.",
    )
