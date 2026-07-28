import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Logging estructurado a stdout (recogido por Fluent Bit/CloudWatch en EKS)."""
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
