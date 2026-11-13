"""Stable, safe errors at application boundaries."""


class AppError(Exception):
    """An error whose message contains no user input or private configuration."""

    code = "APPLICATION_ERROR"


class ConfigurationError(AppError):
    code = "CONFIG_INVALID"


class StorageError(AppError):
    code = "STORAGE_ERROR"


class LockError(StorageError):
    code = "DEPLOYMENT_LOCKED"


class MigrationError(AppError):
    code = "MIGRATION_FAILED"


class DatabaseError(AppError):
    code = "DATABASE_ERROR"

