from dataclasses import replace

import pytest

from mi_boti.domain.discord import (
    ActorContext, RemoteChannel, GuildSnapshot, COMMAND_CHANNELS, REQUIRED_BOT_PERMISSIONS,
    DiscordPolicyError, authorize,
)


def context():
    actor = ActorContext("100", "200", "300")
    remote = RemoteChannel("200", "renamed-channel", "TEXT", None, (), REQUIRED_BOT_PERMISSIONS)
    snapshot = GuildSnapshot("100", "400", (remote,), frozenset(), (), frozenset({"300"}), REQUIRED_BOT_PERMISSIONS)
    options = dict(guild_id="100", owner_ids=("300",), operator_roles=("500",),
                   config={"setup_state": "READY"}, mappings={key: "200" for key in COMMAND_CHANNELS}, snapshot=snapshot)
    return actor, options


@pytest.mark.parametrize("command", COMMAND_CHANNELS)
@pytest.mark.parametrize("failure", ["guild", "dm", "thread", "member", "channel", "mapping", "configuration", "visibility", "bot_permissions"])
def test_every_command_denies_invalid_context(command, failure):
    actor, options = context()
    if failure == "guild": actor = replace(actor, guild_id="999")
    if failure == "dm": actor = replace(actor, guild_id=None, channel_id=None)
    if failure == "thread": actor = replace(actor, text_channel=False)
    if failure == "member": actor = replace(actor, user_id="999")
    if failure == "channel": actor = replace(actor, channel_id="999")
    if failure == "mapping": options["mappings"] = {}
    if failure == "configuration": options["config"] = {"setup_state": "PARTIAL"}
    if failure == "visibility": actor = replace(actor, can_view=False)
    if failure == "bot_permissions":
        old = options["snapshot"]
        options["snapshot"] = replace(old, channels=(replace(old.channels[0], bot_permissions=frozenset()),))
    if command == "setup" and failure in {"mapping", "configuration", "bot_permissions"}:
        # Administrator bootstrap/recovery is explicitly scoped to setup.
        authorize(actor, command, **options)
    else:
        with pytest.raises(DiscordPolicyError):
            authorize(actor, command, **options)


@pytest.mark.parametrize("command", COMMAND_CHANNELS)
def test_owner_and_admin_can_use_each_correct_channel(command):
    actor, options = context()
    authorize(actor, command, **options)
    authorize(replace(actor, user_id="999", administrator=True), command, **options)


@pytest.mark.parametrize("command", COMMAND_CHANNELS)
def test_operator_cannot_use_administrator_actions(command):
    actor, options = context()
    operator = replace(actor, user_id="999", role_ids=frozenset({"500"}))
    if command in {"setup", "config", "backup"}:
        with pytest.raises(DiscordPolicyError): authorize(operator, command, **options)
    else:
        authorize(operator, command, **options)
    if command == "connections":
        with pytest.raises(DiscordPolicyError): authorize(operator, command, admin_action=True, **options)
