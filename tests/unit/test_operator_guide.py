from mi_boti.discord_app.guide import COMMAND_HELP, build_guide_embed
from mi_boti.domain.discord import COMMAND_CHANNELS


def test_guide_covers_every_command_and_resolves_current_channel_ids():
    mappings={key:str(1000+index) for index,key in enumerate(COMMAND_CHANNELS)}
    embed=build_guide_embed({"mappings":mappings})
    assert set(COMMAND_HELP)==set(COMMAND_CHANNELS)
    for command,field in zip(COMMAND_HELP,embed.fields):
        assert f"<#{mappings[command]}>" in field.value
        assert field.name.startswith('/'+command.replace('.', ' '))
    assert len(embed)<=6000 and len(embed.description)<=4096 and len(embed.fields)<=25
    assert all(len(f.name)<=256 and len(f.value)<=1024 for f in embed.fields)
    assert "Disabled" in next(f.value for f in embed.fields if f.name.startswith('/discover '))
    assert "Implemented" in next(f.value for f in embed.fields if f.name.startswith('/research '))


def test_missing_mapping_and_enabled_discovery_are_reported_without_claiming_ai_ready():
    embed=build_guide_embed({"mappings":{}},discovery_enabled=True)
    assert all('Not mapped' in f.value for f in embed.fields)
    assert 'AI and hunting are disabled' in embed.description
    assert 'Enabled' in next(f.value for f in embed.fields if f.name.startswith('/discover '))
