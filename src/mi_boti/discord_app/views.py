"""Persistent controls carry routing hints, never authorization."""

import discord

from ..domain.discord import COMMAND_CHANNELS, PANELS


class SetupConfirmation(discord.ui.View):
    def __init__(self, client, plan_id, digest):
        super().__init__(timeout=None)
        for cancel, label, style in ((False, "Confirm setup", discord.ButtonStyle.success), (True, "Cancel", discord.ButtonStyle.secondary)):
            button = discord.ui.Button(label=label, style=style,
                                       custom_id=f"mb:v1:{'cancel' if cancel else 'confirm'}:{plan_id}:{digest[:16]}")
            async def callback(interaction, cancelled=cancel):
                await client.confirm_setup(interaction, plan_id, digest, cancel=cancelled)
            button.callback = callback
            self.add_item(button)


class PanelView(discord.ui.View):
    def __init__(self, client, key, panel_id, revision, current):
        super().__init__(timeout=None)
        mappings = dict(current["mappings"])
        for command, resource_key in COMMAND_CHANNELS.items():
            resource = current["resources"].get(resource_key)
            if resource and resource["discord_id"]:
                mappings.setdefault(command, resource["discord_id"])
        if key == "dashboard":
            for label, command in (("Tool guide", "guide"), ("Hunt control", "hunt.status"), ("Settings", "setup"), ("Connections", "connections")):
                if command in mappings:
                    self.add_item(discord.ui.Button(label=label, url=f"https://discord.com/channels/{client.settings.guild_id}/{mappings[command]}"))
            return
        command = {"guide": "guide", "hunt_progress": "hunt.status", "usage": "usage", "settings": "setup"}[key]
        own_channel = current["resources"].get(PANELS[key], {}).get("discord_id")
        if command in mappings and mappings[command] != own_channel:
            self.add_item(discord.ui.Button(label="Open assigned command channel", url=f"https://discord.com/channels/{client.settings.guild_id}/{mappings[command]}"))
            return
        button = discord.ui.Button(label="Preview setup" if key == "settings" else "Read tool guide" if key == "guide" else "Refresh status",
                                   custom_id=f"mb:v1:panel:{panel_id}:{revision}")
        async def callback(interaction):
            await client.panel_action(interaction, command, panel_id, revision)
        button.callback = callback
        self.add_item(button)
