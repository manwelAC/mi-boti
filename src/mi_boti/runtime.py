"""Foundation composition root. It never connects Discord or starts jobs."""

from contextlib import ExitStack, contextmanager

from .config import Settings
from .logging import configure_logging, close_logging
from .repositories.database import Database
from .storage.lock import DeploymentLock
from .storage.artifacts import ArtifactStore
from .storage.paths import prepare_data_root, confined


@contextmanager
def initialize(settings: Settings):
    settings.require_identity()
    minimum = settings.values["runtime.minimum_disk_free_mib"]
    root = prepare_data_root(settings.data_dir, minimum_mib=minimum)
    with ExitStack() as stack:
        stack.enter_context(DeploymentLock(confined(root, "deployment.lock")))
        logger = configure_logging(
            confined(root, "logs/mi-boti.log"), secrets=(settings.discord_token,),
            level=settings.values["runtime.log_level"], max_bytes=settings.values["runtime.log_max_bytes"],
            backups=settings.values["runtime.log_backups"],
        )
        stack.callback(close_logging, logger)
        database = stack.enter_context(Database(confined(root, "mi_boti.sqlite3"),
                                               busy_timeout_ms=settings.values["runtime.sqlite_busy_timeout_ms"]))
        database.migrate(minimum_disk_mib=minimum)
        database.bind_guild(settings.guild_id)
        ArtifactStore(root, database, minimum_disk_mib=minimum, retention_days={
            "RESEARCH": settings.values["storage.artifact_ttl_days"],
            "EXPORT": settings.values["storage.export_ttl_days"],
            "VERIFICATION": settings.values["storage.verification_transcript_ttl_days"],
        }).cleanup_orphans(
            max_age_seconds=settings.values["storage.temp_ttl_hours"] * 3600,
        )
        logger.info("Foundation initialized; Discord, discovery, AI and hunting remain inactive.")
        yield database
