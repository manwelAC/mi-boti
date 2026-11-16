"""Operator help rendered from current ID mappings, without executing workflows."""

import discord

# Keys match the canonical registry. Planned tools explain purpose, not fake execution.
COMMAND_HELP = {
    "guide": ("Read this guide", "`/guide` shows a private copy of these instructions.", "ready"),
    "setup": ("Set up or repair the workspace", "Run `/setup`, inspect the proposed changes, then confirm. Repeat runs reuse saved channel IDs. Recovery always needs approval.", "ready"),
    "config": ("Inspect settings", "Use `/config action:view`. To choose a campaign: `/config action:set key:active_campaign_id value:<campaign ID>`.", "ready"),
    "campaign.create": ("Define a search", "Use `/campaign create name:QC Cafes`. Current defaults target a small Quezon City restaurant/cafe test box, not the entire city. Review the bbox before searching.", "campaign"),
    "campaign.list": ("Find campaign IDs", "Use `/campaign list`. Copy the ID from the result for discovery or editing; names alone do not identify a record.", "campaign"),
    "campaign.edit": ("Change a search", "Use `/campaign edit campaign_id:<ID>` and the fields you want to change. Edits create a new campaign version; prior history remains.", "campaign"),
    "discover": ("Find businesses in the local extract", "Once enabled, use `/discover campaign_id:<ID> limit:10`. Results report seen/new/existing/ambiguous/invalid. Existing is a duplicate, not an error; ambiguous needs review. New does not mean qualified.", "discovery"),
    "usage": ("Inspect AI availability", "Use `/usage`. Disabled/unverified means no AI task can run. Login or installation alone does not prove remaining allowance.", "ready"),
    "connections": ("Inspect provider connections", "Use `/connections action:status`. Verification remains gated; this does not log in or execute AI.", "ready"),
    "hunt.status": ("Inspect hunting status", "Use `/hunt status`. Hunting remains disabled; a status reply does not start work.", "ready"),
    "hunt.start": ("Start a quota-based hunt", "Future tool: an authorized start will count only newly qualified unique businesses. No hunting starts on launch or reconnect.", "planned"),
    "hunt.pause": ("Pause a hunt", "Future tool: request a safe checkpoint pause. Currently unavailable.", "planned"),
    "hunt.resume": ("Resume a hunt", "Future tool: explicitly resume after authorization, allowance and budget checks. Currently unavailable.", "planned"),
    "hunt.stop": ("Stop a hunt", "Future tool: stop and receive an accurate partial summary. Currently unavailable.", "planned"),
    "research": ("Collect website evidence", "Future non-AI tool: preserve public observations, source URLs, timestamps and limitations. A missing booking link is not proof of no booking system.", "planned"),
    "qualified": ("Review qualified prospects", "Future tool: list qualified leads with supporting evidence. Discovered businesses are not automatically qualified.", "planned"),
    "leads": ("Browse the CRM", "Future tool: list pipeline records and stages. Discovery alone does not create CRM leads.", "planned"),
    "lead": ("Inspect one business or lead", "Future tool: view history, notes and evidence and resolve ambiguous identities. The Discord identity-review UI is not implemented yet.", "planned"),
    "pipeline": ("Move a lead between stages", "Future tool: update a reviewed lead's stage using revision checks. Currently unavailable.", "planned"),
    "outreach": ("Prepare and review a draft", "Future tool: create, edit and approve outreach drafts. Mi Boti never sends outreach; you review and send it manually.", "planned"),
    "followup": ("Track the next action", "Future tool: record due dates, notes and completion for a lead. Currently unavailable.", "planned"),
    "backup": ("Manage a verified backup", "The Discord workflow is not implemented. Local backup primitives exist; do not assume this command has saved your data.", "planned"),
}


def build_guide_embed(current, *, discovery_enabled=False):
    embed = discord.Embed(
        title="Mi Boti · your tool guide",
        description=(
            "**Start here:** check your settings, create a campaign, then list it to get its ID. "
            "Discovery needs a verified local snapshot and explicit enablement.\n\n"
            "Use each command in the channel shown below. A wrong-channel reply is private and starts no work. "
            "Keep the bot running on your computer; commands cannot reply while it is closed. "
            "Buttons and `/guide` show a private guide without creating jobs.\n\n"
            "**Reading results:** partial means coverage is incomplete; invalid means an observation could not be accepted. "
            "If configuration is incomplete, ask the owner to preview `/setup`. Never paste tokens into Discord.\n\n"
            "**AI and hunting are disabled.** Planned tools below are explanations, not available actions."
        ),
        color=0x88E2CF,
    )
    for command, (purpose, instructions, state) in COMMAND_HELP.items():
        channel_id = current["mappings"].get(command)
        channel = f"<#{channel_id}>" if channel_id else "Not mapped — run /setup"
        status = {"ready": "Available", "campaign": "Implemented · live workflow checks pending",
                  "planned": "Planned · unavailable",
                  "discovery": "Enabled · live operator checks pending" if discovery_enabled else "Disabled · local-source enablement and live checks required"}[state]
        embed.add_field(name=f"/{command.replace('.', ' ')} · {purpose}",
                        value=f"**{status}** · {channel}\n{instructions}", inline=False)
    embed.set_footer(text="New ≠ qualified · duplicates stay remembered · outreach is always manual")
    return embed
