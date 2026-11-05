"""Runtime configuration. Defaults plus env-var overrides; contains no secrets."""
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_API_URL = "https://jsonplaceholder.typicode.com/users"


@dataclass(frozen=True)
class Thresholds:
    """Similarity cutoffs (0.0-1.0) used by the matcher."""
    email_name_min: float = 0.60  # pass 1: email match also needs this name similarity
    name_auto: float = 0.85       # pass 2: auto-match at or above
    name_review: float = 0.70     # pass 2: review band floor
    company_min: float = 0.80     # pass 2: required company similarity


@dataclass(frozen=True)
class Config:
    """Settings for one RecordSync run."""
    api_url: str = DEFAULT_API_URL
    timeout: tuple[float, float] = (3.05, 10.0)  # (connect, read) seconds
    max_retries: int = 3
    backoff_base: float = 0.5
    data_dir: Path = Path("data")
    db_path: Path = Path("data/recordsync.db")
    thresholds: Thresholds = field(default_factory=Thresholds)


def load_config() -> Config:
    """Build a Config; RECORDSYNC_API_URL and RECORDSYNC_DATA_DIR override defaults."""
    data_dir = Path(os.environ.get("RECORDSYNC_DATA_DIR", "data"))
    return Config(
        api_url=os.environ.get("RECORDSYNC_API_URL", DEFAULT_API_URL),
        data_dir=data_dir,
        db_path=data_dir / "recordsync.db",
    )