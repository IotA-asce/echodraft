import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname.lower(),
                "event": record.getMessage(),
                "request_id": getattr(record, "request_id", None),
                "project_id": getattr(record, "project_id", None),
                "job_id": getattr(record, "job_id", None),
                "error": getattr(record, "error", None),
            }
        )


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("echodraft")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
