import os
from pathlib import Path

# tests always run against the repo's real configs
os.environ["BL_CONFIG_DIR"] = str(Path(__file__).resolve().parent.parent / "configs")
# never let the news guard hit the network from tests
os.environ["BL_NEWS_DISABLED"] = "1"
