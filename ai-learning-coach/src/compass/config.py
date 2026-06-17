"""Paths and environment config."""
import os
from pathlib import Path

from dotenv import load_dotenv

# src/compass/config.py → parent = src/compass/ → parent = src/ → parent = ai-learning-coach/
ROOT_DIR: Path = Path(__file__).parent.parent.parent
DATA_DIR: Path = ROOT_DIR / "data"
COMPETENCY_DIR: Path = DATA_DIR / "competency_model"
LEARNERS_DIR: Path = DATA_DIR / "learners"

load_dotenv(ROOT_DIR / ".env")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

# Active learner stored in ~/.compass/active so it persists across working directories
COMPASS_HOME: Path = Path.home() / ".compass"
ACTIVE_LEARNER_FILE: Path = COMPASS_HOME / "active"
