"""
AI Engine — thin wrapper around llama-cpp-python.

Kept isolated from the rest of the app so the model backend could be
swapped later (e.g. for an OpenAI-compatible server) without touching
routes or the prompt builder. Only two things are exposed to the rest
of the app: `load_model(path)` and `generate(prompt, ..., stream=True)`.

If llama-cpp-python (or a compiled model) isn't available, the engine
falls back to a deterministic MockLlama so the rest of the app — DB,
routes, memory, lorebook, frontend — can still be exercised without a
multi-GB GGUF file on disk.
"""
import time
import threading
import os

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
    LLAMA_CPP_ERROR = ""
except Exception as exc:
    # Native DLL loading errors (often CUDA dependencies on Windows) can
    # happen even when the Python package itself is installed. Keep the app
    # runnable and expose the real error through the model-status endpoint.
    LLAMA_CPP_AVAILABLE = False
    LLAMA_CPP_ERROR = f"{type(exc).__name__}: {exc}"

import config


class MockLlama:
    """Stand-in used when llama-cpp-python or a model file isn't
    available yet, so the app is still runnable/testable end to end."""

    def __init__(self, *a, **kw):
        pass

    def create_chat_completion(self, messages, stream=False, max_tokens=512, **kw):
        last_user = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_user = m["content"]
                break
        reply = (
            "[No model loaded — this is a mock reply so you can test the "
            f"pipeline. You said: \"{last_user[:120]}\"]"
        )
        if not stream:
            return {"choices": [{"message": {"content": reply}}]}

        def gen():
            for word in reply.split(" "):
                yield {"choices": [{"delta": {"content": word + " "}}]}
                time.sleep(0.02)
        return gen()

    def tokenize(self, text_bytes, add_bos=False):
        # crude ~4 chars/token estimate, good enough for budgeting
        return list(range(max(1, len(text_bytes) // 4)))


class LLMEngine:
    """Singleton-ish holder for the currently loaded model. One engine
    instance lives on the Flask app; `load_model` swaps the backing
    Llama instance (e.g. when the user picks a different .gguf)."""
    def __init__(self):
        self._llm = None
        self._model_path = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self):
        return self._llm is not None

    @property
    def model_path(self):
        return self._model_path

    def unload_model(self):
        """Release the text model and its native/GPU resources."""
        with self._lock:
            old = self._llm
            self._llm = None
            self._model_path = None
            if old is not None:
                try:
                    del old
                except Exception:
                    pass
            import gc
            gc.collect()

    def load_model(self, path):
        with self._lock:
            if not path:
                self._llm = MockLlama()
                self._model_path = "(mock)"
                return self._model_path

            if not LLAMA_CPP_AVAILABLE:
                raise RuntimeError(
                    "llama-cpp-python could not be loaded. "
                    f"{LLAMA_CPP_ERROR}"
                )

            if not os.path.isfile(path):
                raise FileNotFoundError(f"Model file not found: {path}")

            self._llm = Llama(
                model_path=path,
                n_ctx=config.N_CTX,
                n_gpu_layers=config.N_GPU_LAYERS,
                n_threads=config.N_THREADS,
                verbose=False,
            )
            self._model_path = path
        return self._model_path

    def prepare_for_text(self):
        """Prepare the GPU for the local text model."""
        try:
            from core.image_engine import image_engine
            image_engine.unload()
        except Exception:
            pass

        self.ensure_loaded()

    def ensure_loaded(self):
        if self._llm is None:
            self.load_model(config.DEFAULT_MODEL_PATH)

    def count_tokens(self, text):
        self.ensure_loaded()
        try:
            return len(self._llm.tokenize(text.encode("utf-8", errors="ignore")))
        except Exception:
            return max(1, len(text) // 4)

    def generate(self, messages, temperature=None, top_p=None, top_k=None,
                 repeat_penalty=None, max_tokens=None, stream=True):
        """messages: list of {"role": ..., "content": ...} in llama.cpp
        chat-completion format. Yields text deltas when stream=True,
        otherwise returns the full string."""
        self.prepare_for_text()
        kwargs = dict(
            messages=messages,
            temperature=temperature if temperature is not None else config.DEFAULT_TEMPERATURE,
            top_p=top_p if top_p is not None else config.DEFAULT_TOP_P,
            top_k=top_k if top_k is not None else config.DEFAULT_TOP_K,
            repeat_penalty=repeat_penalty if repeat_penalty is not None else config.DEFAULT_REPEAT_PENALTY,
            max_tokens=max_tokens if max_tokens is not None else config.DEFAULT_MAX_TOKENS,
        )

        if not stream:
            result = self._llm.create_chat_completion(stream=False, **kwargs)
            return result["choices"][0]["message"]["content"]

        def token_stream():
            for chunk in self._llm.create_chat_completion(stream=True, **kwargs):
                delta = chunk["choices"][0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    yield piece

        return token_stream()


engine = LLMEngine()
