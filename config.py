import os
from os import getenv

# Quick mode for fast experiments (reduces estimators, etc.)
QUICK_RUN = getenv("STOCK5_QUICK", "0") == "1"

# Paths (can be overridden via env)
DB_PATH = getenv("STOCK5_DB", r"E:\stock5\stocks.db")
CSV_PATH = getenv("STOCK5_CSV", r"E:\stock5\波段股票Top30.csv")
MODEL_CACHE_DIR = getenv("STOCK5_CACHE", r"E:\stock5\v6\model_cache_v6")
OUTPUT_JSON = getenv("STOCK5_OUTPUT", r"E:\stock5\result_v6.json")

# Cache / retrain control
USE_MODEL_CACHE = getenv("STOCK5_USE_CACHE", "1") == "1"
RETRAIN_FORCE = getenv("STOCK5_RETRAIN", "0") == "1"

# Model/training defaults (tunable via env)
DEFAULT_N = "50" if QUICK_RUN else "200"
N_ESTIMATORS = int(getenv("STOCK5_N_ESTIMATORS", DEFAULT_N))
RISE_THRESHOLD = float(getenv("STOCK5_RISE_THRESHOLD", "0.009"))
PREDICT_DAYS = int(getenv("STOCK5_PREDICT_DAYS", "1"))

# Misc
CACHE_FILENAME = getenv("STOCK5_CACHE_FILE", "models_v6.pkl")
