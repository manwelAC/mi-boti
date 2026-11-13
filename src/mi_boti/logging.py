"""Redaction at the final rendering boundary, including formatted tracebacks."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re

from .storage.paths import reject_links


class Redactor:
    def __init__(self, secrets=()):
        self._secrets = tuple(sorted({x for x in secrets if x}, key=len, reverse=True))

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")
        text = re.sub(r"(?i)\b(Bearer|Basic)\s+[^\s,;\"']+", r"\1 [REDACTED]", text)
        text = re.sub(
            r"(?i)([\"']?(?:[\w-]*(?:token|password|secret|api[_-]?key)|authorization)[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)",
            r"\1[REDACTED]", text,
        )
        # Common Discord bot token shapes, independently of the active value.
        return re.sub(r"\b(?:mfa\.[\w-]{20,}|[\w-]{23,28}\.[\w-]{6}\.[\w-]{25,})\b", "[REDACTED]", text)


class RedactingFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor):
        super().__init__("%(asctime)sZ %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S")
        import time
        self.converter = time.gmtime
        self.redactor = redactor

    def format(self, record):
        return self.redactor.redact(super().format(record))


def configure_logging(log_path: Path, *, secrets=(), level="INFO", max_bytes=5242880, backups=5):
    reject_links(log_path)
    handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    handler.setFormatter(RedactingFormatter(Redactor(secrets)))
    logger = logging.getLogger("mi_boti")
    for previous in logger.handlers[:]:
        logger.removeHandler(previous)
        previous.close()
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
