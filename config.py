"""newAIr configuration."""
import os
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DATA_DIR=os.path.join(BASE_DIR,"data")
DB_PATH=os.path.join(DATA_DIR,"newair.db")
MODELS_DIR=os.environ.get("NEWAIR_MODELS_DIR",os.path.join(BASE_DIR,"models_dir"))
IMAGE_MODELS_DIR=os.environ.get("NEWAIR_IMAGE_MODELS_DIR",os.path.join(BASE_DIR,"image_models"))
INPAINT_MODELS_DIR=os.environ.get("NEWAIR_INPAINT_MODELS_DIR",os.path.join(IMAGE_MODELS_DIR,"inpainting"))
LORA_MODELS_DIR=os.environ.get("NEWAIR_LORA_MODELS_DIR",os.path.join(BASE_DIR,"loras"))
IP_ADAPTER_DIR=os.environ.get("NEWAIR_IP_ADAPTER_DIR",os.path.join(BASE_DIR,"models","ip_adapter","faceid"))
IP_ADAPTER_IMAGE_ENCODER_DIR=os.path.join(IP_ADAPTER_DIR,"image_encoder")
INSIGHTFACE_DIR=os.environ.get("NEWAIR_INSIGHTFACE_DIR",os.path.join(BASE_DIR,"models","insightface"))
GENERATED_IMAGES_DIR=os.environ.get("NEWAIR_GENERATED_IMAGES_DIR",os.path.join(BASE_DIR,"static","generated"))
PERSONA_NAME_DEFAULT=os.environ.get("NEWAIR_PERSONA_NAME","You")
DEFAULT_MODEL_PATH=os.environ.get("NEWAIR_MODEL_PATH","")
if not DEFAULT_MODEL_PATH and os.path.isdir(MODELS_DIR):
    files=[os.path.join(MODELS_DIR,n) for n in sorted(os.listdir(MODELS_DIR)) if n.lower().endswith(".gguf")]
    DEFAULT_MODEL_PATH=files[0] if files else ""
N_CTX=int(os.environ.get("NEWAIR_N_CTX",4096))
N_GPU_LAYERS=int(os.environ.get("NEWAIR_N_GPU_LAYERS",-1))
N_THREADS=int(os.environ.get("NEWAIR_N_THREADS",os.cpu_count() or 4))
RESERVED_FOR_REPLY=512
MAX_STATIC_CONTEXT_TOKENS=1200
MAX_LOREBOOK_ENTRIES_INJECTED=6
# Rolling-memory controls. Full chat history remains in SQLite, but only a
# compact summary plus recent raw messages are sent to the LLM.
MEMORY_SUMMARY_MAX_TOKENS=450
RAW_HISTORY_TARGET_TOKENS=1400
KEEP_RAW_MESSAGES=10
CONTEXT_SAFETY_MARGIN=256
SUMMARIZE_EVERY_N_MESSAGES=20
DEFAULT_TEMPERATURE=.8
DEFAULT_TOP_P=.9
DEFAULT_TOP_K=40
DEFAULT_REPEAT_PENALTY=1.1
DEFAULT_MAX_TOKENS=512
MAX_IMAGE_UPLOAD_MB=12
SECRET_KEY=os.environ.get("NEWAIR_SECRET_KEY","dev-key-change-me")
