"""Isolated CRM facade. Inject fresh authorization; no Discord registration yet."""

from ..domain.crm import CrmError
from ..domain.discord import ActorContext
from ..domain.values import snowflake
from ..repositories import crm


class ManualCrmService:
    def __init__(self, database, authorize, *, guild_id, owner_ids):
        self.database, self.authorize = database, authorize
        self.guild_id = snowflake(guild_id)
        self.owner_ids = frozenset(snowflake(value) for value in owner_ids)

    async def _context(self, command):
        actor = await self.authorize(command)
        if not isinstance(actor, ActorContext) or actor.guild_id != self.guild_id or not actor.text_channel or not actor.can_view:
            raise CrmError("CRM requires a currently authorized member in this guild's mapped text channel.")
        snowflake(actor.user_id)
        snowflake(actor.channel_id)
        def guard(c):
            config = c.execute("SELECT guild_id,setup_state FROM guild_config WHERE id='guild'").fetchone()
            mapping = c.execute("SELECT r.discord_id FROM command_channels m JOIN discord_resources r ON r.id=m.resource_id "
                                "WHERE m.command_key=? AND r.state='ACTIVE' AND r.kind='TEXT' AND r.guild_id=?", (command, self.guild_id)).fetchone()
            if not config or config[0] != self.guild_id or config[1] != "READY" or not mapping or mapping[0] != actor.channel_id:
                raise CrmError("CRM configuration or channel mapping changed; retry in the assigned channel.")
            roles = {row[0] for row in c.execute("SELECT role_id FROM role_grants WHERE permission='OPERATOR'")}
            if actor.user_id not in self.owner_ids and not actor.administrator and not roles.intersection(actor.role_ids):
                raise CrmError("Current CRM operator authorization is required.")
        return actor, guard

    async def qualify_manual(self, business_id, *, confirmed=False, **options):
        actor, guard = await self._context("lead")
        if confirmed is not True: raise CrmError("Explicit confirmation of the manual evidence review is required.")
        return await self.database.call(lambda db: crm.qualify_manual(db, business_id, actor.user_id, _guard=guard, **options))

    async def transition(self, lead_id, *, confirmed=False, **options):
        actor, guard = await self._context("pipeline")
        if confirmed is not True: raise CrmError("Explicit confirmation of the pipeline action is required.")
        return await self.database.call(lambda db: crm.transition(db, lead_id, actor.user_id, _guard=guard, **options))

    async def add_note(self, lead_id, **options):
        actor, guard = await self._context("lead")
        return await self.database.call(lambda db: crm.add_note(db, lead_id, actor.user_id, _guard=guard, **options))

    async def _read(self, command, function):
        _, guard = await self._context(command)
        def read(db):
            with db.transaction() as c:
                guard(c)
                return function(db)
        return await self.database.call(read)

    async def get_lead(self, lead_id):
        return await self._read("lead", lambda db: crm.get_lead(db, lead_id))

    async def list_leads(self, *, stage=None, page=1):
        return await self._read("leads", lambda db: crm.list_records(db, stage=stage, page=page))

    async def history(self, lead_id, *, notes=False, page=1):
        return await self._read("lead", lambda db: crm.list_records(db, lead_id=lead_id, kind="lead_notes" if notes else "lead_events", page=page))
