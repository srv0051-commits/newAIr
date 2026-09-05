"""
newAIr — configuration.

Everything here can be overridden with environment variables so the
app can be pointed at different model files / context sizes without
touching code.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Storage -----------------------------------------------------------
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "newair.db")
MODELS_DIR = os.environ.get("NEWAIR_MODELS_DIR", os.path.join(BASE_DIR, "models_dir"))
IMAGE_MODELS_DIR = os.environ.get("NEWAIR_IMAGE_MODELS_DIR", os.path.join(BASE_DIR, "image_models"))
GENERATED_IMAGES_DIR = os.environ.get("NEWAIR_GENERATED_IMAGES_DIR", os.path.join(BASE_DIR, "static", "generated"))
PERSONA_NAME_DEFAULT = os.environ.get("NEWAIR_PERSONA_NAME", "You")

# --- LLM engine ----------------------------------------------------------
# Path to a .gguf file. Left unset until the user loads one via
# /api/models/load or drops a file in models_dir/ and picks it in the UI.
DEFAULT_MODEL_PATH = os.environ.get("NEWAIR_MODEL_PATH", "")
if not DEFAULT_MODEL_PATH:
    # Prefer a bundled/local GGUF automatically so a fresh install does not
    # silently fall back to the mock engine when a model is already present.
    _gguf_files = [
        os.path.join(MODELS_DIR, name)
        for name in sorted(os.listdir(MODELS_DIR))
        if name.lower().endswith(".gguf")
    ] if os.path.isdir(MODELS_DIR) else []
    DEFAULT_MODEL_PATH = _gguf_files[0] if _gguf_files else ""

N_CTX = int(os.environ.get("NEWAIR_N_CTX", 4096))          # total context window (tokens)
# -1 = offload all possible layers to the GPU. This is the tested configuration
# for the current RTX 3050 6GB + Dolphin 3.0 8B Q4_K_M setup.
N_GPU_LAYERS = int(os.environ.get("NEWAIR_N_GPU_LAYERS", -1))
N_THREADS = int(os.environ.get("NEWAIR_N_THREADS", os.cpu_count() or 4))

# --- Prompt / context budgeting ------------------------------------------
# Rough token budget split. RESERVED_FOR_REPLY is subtracted from N_CTX
# before anything else; the remainder is shared between static context
# (character card + lorebook + memories) and recent chat history.
RESERVED_FOR_REPLY = 512
MAX_STATIC_CONTEXT_TOKENS = 1200   # character + scenario + lorebook + memory summary
MAX_LOREBOOK_ENTRIES_INJECTED = 6

# --- Memory ---------------------------------------------------------------
# After this many *new* messages since the last summary, the memory
# manager rolls them into a running summary instead of keeping raw text.
SUMMARIZE_EVERY_N_MESSAGES = 20
# How many of the most recent raw messages are always kept verbatim
# (never summarized away), regardless of the counter above.
KEEP_RAW_MESSAGES = 12

# --- Generation defaults ---------------------------------------------------
DEFAULT_TEMPERATURE = 0.8
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 40
DEFAULT_REPEAT_PENALTY = 1.1
DEFAULT_MAX_TOKENS = 512

SECRET_KEY = os.environ.get("NEWAIR_SECRET_KEY", "dev-key-change-me")
