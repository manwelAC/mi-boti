import io
import logging

from mi_boti.logging import Redactor, RedactingFormatter, configure_logging


def test_redacts_known_secrets_json_headers_and_tracebacks():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(RedactingFormatter(Redactor(["fixture-live-token"])))
    logger = logging.Logger("redaction-test")
    logger.addHandler(handler)
    try:
        raise RuntimeError('Bearer auth-secret password="private-pass" {"api_key":"private-key"}')
    except RuntimeError:
        logger.exception("active %s", "fixture-live-token")
    text = output.getvalue()
    assert "[REDACTED]" in text
    for secret in ["fixture-live-token", "auth-secret", "private-pass", "private-key"]:
        assert secret not in text


def test_logging_rotation_is_bounded_and_redacted(tmp_path):
    path = tmp_path / "runtime.log"
    logger = configure_logging(path, secrets=["secret-value"], max_bytes=100, backups=2)
    for _ in range(10):
        logger.info("secret-value plus safe context " * 3)
    for h in logger.handlers:
        h.close()
    files = list(tmp_path.glob("runtime.log*"))
    assert 1 <= len(files) <= 3
    assert all("secret-value" not in f.read_text(encoding="utf-8") for f in files)


def test_discord_route_tokens_are_redacted_through_sdk_logger(tmp_path):
    from mi_boti.logging import close_logging
    path = tmp_path / "safe-sdk.log"
    logger = configure_logging(path)
    logging.getLogger("discord.http").warning("POST https://discord.com/api/v10/webhooks/123/route-secret")
    logging.getLogger("discord.webhook.async_").warning("POST /interactions/456/interaction-secret/callback")
    close_logging(logger)
    text = path.read_text(encoding="utf-8")
    assert "route-secret" not in text and "interaction-secret" not in text
    assert text.count("[REDACTED]") == 2
