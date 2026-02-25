import discord

def clamp(n: int, low: int, high: int) -> int:
    return max(low, min(high, n))

def admin_only(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.administrator)
