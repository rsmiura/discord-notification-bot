"""Slash commands translate Discord interactions into service calls."""

import discord
from discord import app_commands

from notifications import LiveNotifier
from state import StateError


def register_commands(tree: app_commands.CommandTree, notifier: LiveNotifier) -> None:
    @tree.command(name="ping", description="Check whether the bot is responding.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong!")

    @tree.command(name="set-role", description="Choose the role used for notifications.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role="The role to ping for notifications")
    async def set_role(interaction: discord.Interaction, role: discord.Role) -> None:
        if role.is_default():
            await interaction.response.send_message("Choose a role other than @everyone.", ephemeral=True)
            return
        if interaction.guild_id is None or interaction.channel_id is None:
            return
        try:
            notifier.store.set_destination(interaction.guild_id, role.id, interaction.channel_id)
        except StateError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Notification role set to {role.mention}. Live alerts will be sent in this channel.",
            allowed_mentions=discord.AllowedMentions.none(), ephemeral=True,
        )

    @tree.command(name="test-live", description="Send a test livestream notification.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def test_live(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            return
        try:
            sent = await notifier.send_test(interaction.guild_id)
            message = (
                "Test notification sent using the live notification function."
                if sent else
                "I could not send the test. Run `/set-role` in the alert channel first and check bot permissions."
            )
        except (ValueError, StateError) as error:
            message = str(error)
        await interaction.followup.send(message, ephemeral=True)
