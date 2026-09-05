# newAIr

A local, self-hosted character-chat app powered by `llama.cpp` (via
`llama-cpp-python`), with character cards, a keyword-triggered
lorebook, rolling long-term memory, and full chat controls
(edit / regenerate / continue) — all backed by SQLite, no cloud
dependency.

```
newAIr/
├── app.py                  Flask entry point
├── config.py                All tunables (context size, budgets, sampling defaults)
├── core/
│   ├── database.py          SQLite schema + connection helpers
│   ├── llm_engine.py         llama-cpp-python wrapper (+ mock fallback)
│   ├── memory_manager.py     rolling conversation summaries + durable facts
│   ├── lorebook.py           keyword-triggered world info
│   └── prompt_builder.py     assembles the final prompt within the token budget
├── routes/
│   ├── characters.py        character CRUD, character memory, lorebook API
│   ├── chat.py               conversations, streaming chat, edit/regen/continue
│   └── models.py             list/load .gguf files
├── static/{css,js}/          frontend (vanilla JS, no build step)
├── templates/index.html
├── models_dir/                drop your .gguf files here
└── data/newair.db             created automatically on first run
```

## 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`llama-cpp-python` compiles a native extension on install. For GPU
acceleration, install it with the appropriate backend flag instead of
the plain PyPI wheel, e.g. for CUDA:

```bash
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
```

(Metal on macOS: `-DGGML_METAL=on`. See the llama-cpp-python docs for
the full list of backends.)

If `llama-cpp-python` isn't installed, or no model is loaded, the app
still runs — it falls back to a mock engine that echoes back a canned
reply, so you can build/test characters, lorebook, and the UI without
a model file.

## 2. Get a model

Download any GGUF chat model (e.g. from Hugging Face — search for
`GGUF` builds of a model you like) and place the `.gguf` file in
`models_dir/`. A 7–8B instruct model in Q4_K_M quantization is a
reasonable starting point for a CPU-only machine.

## 3. Run

```bash
python app.py
```

Open http://127.0.0.1:5000. In the sidebar, click **⚙ Model**, and
load the `.gguf` file you placed in `models_dir/`.

## 4. Usage notes

- **Characters**: name, personality, scenario, greeting, and example
  dialogue make up the character card, injected as the system prompt
  on every turn.
- **Lorebook**: entries only get injected into the prompt when one of
  their keywords appears in the recent conversation — keeps the
  always-on context small even with a large lore set. Entries can be
  character-specific or global.
- **Memory**: two tiers —
  - *Character memory* (🧠 button): durable facts always included,
    never summarized away (e.g. "user's name is John").
  - *Conversation memory*: automatic — once a chat passes
    `SUMMARIZE_EVERY_N_MESSAGES` (config.py), the oldest messages are
    compressed into a running summary by the model itself, keeping
    the context bounded on long chats instead of just truncating.
- **Edit / Regenerate / Continue**: hover a message to edit or delete
  it; use the header buttons to regenerate the last reply or have the
  model continue its previous message.
- All tunables — context window size, token budgets, summarization
  thresholds, sampling defaults — live in `config.py`, overridable via
  environment variables (see comments in that file).

## 5. Extending it

- Swap backends: `core/llm_engine.py` is the only file that knows
  about llama.cpp specifically — point it at an OpenAI-compatible
  server instead and nothing else needs to change.
- The DB schema (`core/database.py`) has room for more: `avatar_path`
  is already wired for character images if you add file upload.


## newAIr local CUDA setup

The application is designed to load GGUF models directly through `llama-cpp-python`; LM Studio or Ollama is not required.

For the current tested setup (Windows + NVIDIA RTX 3050 6GB), install the CUDA-enabled wheel that matches your environment, then run newAIr from the same activated virtual environment. The app defaults to `n_gpu_layers=-1` and `n_ctx=4096`, which are configurable with `NEWAIR_N_GPU_LAYERS` and `NEWAIR_N_CTX`.

Put `.gguf` files in `models_dir/`. If no `NEWAIR_MODEL_PATH` environment variable is set, newAIr automatically selects the first `.gguf` file in that folder.


## newAIr 0.2 architecture
- Assistant Mode: normal local AI chat using a selected user persona.
- Character Mode: character cards, scenarios, memories, lorebook, and explicit user identity.
- Personas: reusable user identity/profile shared across chats.
- Image Studio: local Diffusers backend scaffold; place a compatible local model directory under image_models/.
- LLM: llama-cpp-python with GGUF and GPU offload via config.

### Important
The image backend is intentionally optional. The exact install command/model loader depends on the image model you download. For a 6 GB RTX 3050, prefer a lightweight SD 1.5-class model or an optimized low-VRAM workflow rather than assuming a large FLUX/SDXL model will fit comfortably.
