import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_SECRET_PARAM = re.compile(r"(?i)(api_key|apikey|api-key|token|access_token)=([^&\s]+)")
_SECRET_JSON = re.compile(r'(?i)"(api_key|apikey|api-key|token|access_token)"\s*:\s*"[^"]*"')


def redact(text: str, secrets: list[str] | None = None) -> str:
    cleaned = _SECRET_PARAM.sub(r"\1=REDACTED", text)
    cleaned = _SECRET_JSON.sub(r'"\1":"REDACTED"', cleaned)
    for secret in secrets or []:
        if secret and secret in cleaned:
            cleaned = cleaned.replace(secret, "REDACTED")
    return cleaned


class JsonFormatter(logging.Formatter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self._secrets = [secret for secret in (secrets or []) if secret]

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "message": redact(record.getMessage(), self._secrets),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            for key, value in fields.items():
                if key.lower() in {"api_key", "token", "apify_token", "hunter_api_key"}:
                    continue
                payload[key] = value
        if record.exc_info:
            payload["error"] = redact(self.formatException(record.exc_info), self._secrets)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    verbose: bool,
    secrets: list[str] | None = None,
    log_path: Path | None = None,
) -> logging.Logger:
    logger = logging.getLogger("roofleads")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.DEBUG)
    formatter = JsonFormatter(secrets)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    stream = logging.StreamHandler(sys.stderr)
    stream.setLevel(logging.DEBUG if verbose else logging.WARNING)
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    logger.propagate = False
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logger
