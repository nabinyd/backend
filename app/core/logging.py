import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(app_name: str = "agribot-backend"):
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    logger = logging.getLogger()
    logger.setLevel(level)

    # Prevent duplicate handlers (important for reload)
    if logger.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Optional: rotating file logs
    log_file = os.getenv("LOG_FILE", "")
    if log_file:
        fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3)
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logging.getLogger(app_name).info("Logging initialized (level=%s)", level)
