"""Local image generation engine for SDXL/Pony .safetensors checkpoints.

Long prompts are supported through Compel, which chunks prompts beyond
CLIP's normal 77-token context instead of silently truncating them.
"""
import gc
import os
from PIL import Image
import base64, io
import threading
import uuid
import config
import torch


class ImageEngine:
    def __init__(self):
        self.pipe = None
        self.model_path = None
        self.model_type = None
        self.error = ""
        self._lock = threading.Lock()

    @property
    def available(self):
        try:
            import torch
            import diffusers
            return True
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            return False

    def list_models(self):
        os.makedirs(config.IMAGE_MODELS_DIR, exist_ok=True)
        items = []
        for name in sorted(os.listdir(config.IMAGE_MODELS_DIR)):
            path = os.path.join(config.IMAGE_MODELS_DIR, name)
            if os.path.isdir(path) or name.lower().endswith((".safetensors", ".ckpt")):
                items.append(name)
        return items

    def _unload_current(self):
        if self.pipe is not None:
            try:
                del self.pipe
            except Exception:
                pass

        self.pipe = None
        self.model_path = None
        self.model_type = None
        gc.collect()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

    def unload(self):
        with self._lock:
            self._unload_current()
            self.error = ""

    def load(self, name):
        path = os.path.join(config.IMAGE_MODELS_DIR, name)

        if not (os.path.isdir(path) or os.path.isfile(path)):
            raise FileNotFoundError(path)

        try:
            import torch
            from diffusers import (
                AutoPipelineForText2Image,
                StableDiffusionXLPipeline,
                StableDiffusionPipeline,
            )
        except Exception as e:
            raise RuntimeError(
                "Install the image backend: "
                "pip install torch diffusers transformers accelerate safetensors Pillow"
            ) from e

        # The RTX 3050 has 6 GB VRAM. Free Dolphin before loading SDXL/Pony.
        try:
            from core.llm_engine import engine as text_engine
            text_engine.unload_model()
        except Exception:
            pass

        with self._lock:
            self._unload_current()

            dtype = torch.float16 if torch.cuda.is_available() else torch.float32

            if os.path.isfile(path):
                if not path.lower().endswith((".safetensors", ".ckpt")):
                    raise ValueError("Image model must be a .safetensors or .ckpt file.")

                # Realistic Vision V6 is an SD 1.5 checkpoint. The previous
                # version tried SDXL first, and Diffusers could sometimes
                # construct an SDXL pipeline with incomplete components
                # instead of failing cleanly. That later caused:
                #   AttributeError: 'NoneType' object has no attribute 'tokenize'
                #
                # Use the known checkpoint family to select the correct
                # pipeline up front.
                lower_name = os.path.basename(path).lower()
                is_sd15 = any(marker in lower_name for marker in (
                    "realisticvision",
                    "realistic_vision",
                    "realistic-vision",
                    "v60b1",
                    "v5.1vae",
                    "v51vae",
                ))

                is_inpaint = any(marker in lower_name for marker in (
                    "inpaint", "inpainting", "in-paint"
                ))

                if is_sd15 and is_inpaint:
                    from diffusers import StableDiffusionInpaintPipeline
                    pipe = StableDiffusionInpaintPipeline.from_single_file(
                        path,
                        torch_dtype=dtype,
                        local_files_only=True,
                        use_safetensors=path.lower().endswith(".safetensors"),
                    )
                elif is_sd15:
                    pipe = StableDiffusionPipeline.from_single_file(
                        path,
                        torch_dtype=dtype,
                        local_files_only=True,
                        use_safetensors=path.lower().endswith(".safetensors"),
                    )
                else:
                    pipe = StableDiffusionXLPipeline.from_single_file(
                        path,
                        torch_dtype=dtype,
                        local_files_only=True,
                        use_safetensors=path.lower().endswith(".safetensors"),
                    )
            else:
                if "inpaint" in os.path.basename(path).lower():
                    try:
                        from diffusers import AutoPipelineForInpainting
                        pipe = AutoPipelineForInpainting.from_pretrained(
                            path, torch_dtype=dtype, local_files_only=True
                        )
                    except Exception:
                        pipe = AutoPipelineForText2Image.from_pretrained(
                            path, torch_dtype=dtype, local_files_only=True
                        )
                else:
                    pipe = AutoPipelineForText2Image.from_pretrained(
                        path, torch_dtype=dtype, local_files_only=True
                    )

            # Memory optimizations for RTX 3050 6GB.
            if hasattr(pipe, "vae"):
                if hasattr(pipe.vae, "enable_slicing"):
                    pipe.vae.enable_slicing()
                if hasattr(pipe.vae, "enable_tiling"):
                    pipe.vae.enable_tiling()

            # Prefer PyTorch 2.x scaled-dot-product attention when available.
            # This is substantially more VRAM-friendly than the legacy
            # attention-slicing path for larger SD 1.5 images.
            try:
                from diffusers.models.attention_processor import AttnProcessor2_0
                if hasattr(pipe, "unet"):
                    pipe.unet.set_attn_processor(AttnProcessor2_0())
            except Exception:
                pass

            if torch.cuda.is_available():
                # Compel needs to call the CLIP text encoders directly when
                # building long-prompt embeddings. Sequential CPU offload
                # places those encoders behind Accelerate hooks and can leave
                # Compel hitting meta tensors. Keep the text encoders as real
                # CPU modules and sequentially offload only the heavy
                # generation components.
                #
                # We intentionally do not call pipe.enable_sequential_cpu_offload()
                # on the whole pipeline here.
                try:
                    text_encoders = []
                    for attr in ("text_encoder", "text_encoder_2"):
                        encoder = getattr(pipe, attr, None)
                        if encoder is not None:
                            text_encoders.append(encoder)
                            encoder.to("cpu")

                    # Offload the heavy components individually. This avoids
                    # installing Accelerate hooks on the CLIP encoders while
                    # still keeping UNet/VAE memory usage low.
                    from accelerate import cpu_offload

                    execution_device = torch.device("cuda")

                    for component_name in ("unet", "transformer", "vae"):
                        component = getattr(pipe, component_name, None)
                        if component is not None:
                            cpu_offload(
                                component,
                                execution_device=execution_device,
                            )

                except Exception as exc:
                    raise RuntimeError(
                        "Could not configure selective CPU offloading for "
                        "the image pipeline. Whole-pipeline sequential "
                        "offloading is intentionally not used because it "
                        "conflicts with Compel long-prompt encoding."
                    ) from exc
            else:
                pipe.to("cpu")

            self.pipe = pipe
            self.model_path = path
            self.model_type = type(pipe).__name__
            self.error = ""

        return path

    def _truncate_for_tokenizer(self, text, tokenizer):
        """
        CLIP normally accepts at most 77 token positions.

        Diffusers otherwise prints a warning and silently truncates long
        prompts. We do the truncation ourselves so the user gets no CLIP
        indexing warning and the generated prompt is deterministic.

        The tokenizer's own model_max_length is used instead of hard-coding
        77 so this also works with compatible pipelines using another limit.
        """
        if not text or tokenizer is None:
            return text

        max_length = getattr(tokenizer, "model_max_length", 77)

        # Some tokenizers report an absurdly large sentinel value.
        if not isinstance(max_length, int) or max_length <= 0 or max_length > 4096:
            max_length = 77

        encoded = tokenizer(
            text,
            truncation=True,
            max_length=max_length,
            padding=False,
            return_tensors=None,
        )

        input_ids = encoded.get("input_ids")
        if input_ids is None:
            return text

        # If nothing was truncated, preserve the original text exactly.
        if len(input_ids) <= max_length:
            return text

        # Decode the truncated token IDs back into text.
        return tokenizer.decode(
            input_ids[:max_length],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        )

    def _prepare_prompt(self, text):
        """
        Keep the user's complete prompt intact.

        Long prompts are handled by Compel in _build_prompt_embeddings().
        This prevents the normal CLIP 77-token truncation.
        """
        if text is None:
            return ""
        return str(text).strip()

    def _build_prompt_embeddings(self, prompt, negative_prompt=""):
        """
        Build prompt embeddings with Compel.

        Compel chunks long prompts instead of silently discarding everything
        after CLIP's normal 77-token context window.

        SDXL returns prompt + negative + pooled embeddings.
        SD 1.5 returns prompt + negative embeddings.
        """
        if self.pipe is None:
            raise RuntimeError("No image model loaded.")

        try:
            from compel import CompelForSD, CompelForSDXL
        except ImportError as exc:
            raise RuntimeError(
                "Long-prompt support requires the 'compel' package. "
                "Open your terminal and run: pip install -U compel"
            ) from exc

        prompt = self._prepare_prompt(prompt)
        negative_prompt = self._prepare_prompt(negative_prompt)

        # The CLIP text encoders are intentionally kept on CPU because the
        # image pipeline selectively offloads only the heavy generation
        # components. Compel therefore builds the embeddings on CPU, and we
        # move only the small resulting tensors to CUDA afterward.
        #
        # CompelForSDXL/CompelForSD are used instead of the older multi-list
        # Compel constructor. These wrappers have long-prompt support enabled
        # by default and avoid the deprecation warning in Compel 2.4.x.
        if self.model_type == "StableDiffusionXLPipeline":
            if not all(
                (
                    getattr(self.pipe, "tokenizer", None),
                    getattr(self.pipe, "tokenizer_2", None),
                    getattr(self.pipe, "text_encoder", None),
                    getattr(self.pipe, "text_encoder_2", None),
                )
            ):
                raise RuntimeError(
                    "The loaded SDXL model is missing a tokenizer or text encoder."
                )

            compel = CompelForSDXL(
                pipe=self.pipe,
                device="cpu",
            )

            # Encode positive and negative prompts independently.
            # This avoids any ambiguity in Compel's combined prompt API and
            # guarantees the negative text only becomes negative embeddings.
            positive = compel(prompt)
            negative = compel(negative_prompt or "")

            target_device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )

            target_dtype = None
            if target_device.type == "cuda":
                try:
                    target_dtype = self.pipe.unet.dtype
                except Exception:
                    target_dtype = torch.float16

            def move_embedding(tensor):
                if tensor is None:
                    return None
                if target_dtype is not None and tensor.is_floating_point():
                    return tensor.to(
                        device=target_device,
                        dtype=target_dtype,
                    )
                return tensor.to(device=target_device)

            return (
                move_embedding(positive.embeds),
                move_embedding(negative.embeds),
                move_embedding(positive.pooled_embeds),
                move_embedding(negative.pooled_embeds),
            )

        if self.model_type == "StableDiffusionPipeline":
            if not all(
                (
                    getattr(self.pipe, "tokenizer", None),
                    getattr(self.pipe, "text_encoder", None),
                )
            ):
                raise RuntimeError(
                    "The loaded image model is missing its tokenizer or text encoder."
                )

            compel = CompelForSD(
                pipe=self.pipe,
                device="cpu",
            )

            # Encode positive and negative prompts independently.
            # This avoids any ambiguity in Compel's combined prompt API and
            # guarantees the negative text only becomes negative embeddings.
            positive = compel(prompt)
            negative = compel(negative_prompt or "")

            target_device = torch.device(
                "cuda" if torch.cuda.is_available() else "cpu"
            )

            target_dtype = None
            if target_device.type == "cuda":
                try:
                    target_dtype = self.pipe.unet.dtype
                except Exception:
                    target_dtype = torch.float16

            def move_embedding(tensor):
                if tensor is None:
                    return None
                if target_dtype is not None and tensor.is_floating_point():
                    return tensor.to(
                        device=target_device,
                        dtype=target_dtype,
                    )
                return tensor.to(device=target_device)

            return (
                move_embedding(positive.embeds),
                move_embedding(negative.embeds),
            )

        raise RuntimeError(
            f"Long-prompt embedding is not supported for {self.model_type}."
        )


    def img2img(
        self,
        prompt,
        negative_prompt="",
        image_data="",
        strength=0.55,
        steps=20,
        guidance=5.0,
        seed=-1,
    ):
        """Edit an input image using the currently loaded SD1.5/SDXL model."""
        if self.pipe is None:
            raise RuntimeError("No image model loaded.")

        try:
            import base64
            import io
            import torch
            from diffusers import (
                StableDiffusionImg2ImgPipeline,
                StableDiffusionXLImg2ImgPipeline,
            )

            if not isinstance(image_data, str) or "," not in image_data:
                raise ValueError("Valid source image data is required.")

            raw = base64.b64decode(image_data.split(",", 1)[1])
            image = Image.open(io.BytesIO(raw)).convert("RGB")

            # Keep editing practical on a 6 GB GPU.
            scale = min(1.0, 1024.0 / max(image.width, image.height))
            width = max(256, (int(image.width * scale) // 8) * 8)
            height = max(256, (int(image.height * scale) // 8) * 8)
            # Keep img2img within a safer ~0.8 MP budget for 6 GB GPUs.
            if width * height > 786432:
                scale = (786432.0 / (width * height)) ** 0.5
                width = max(256, (int(width * scale) // 8) * 8)
                height = max(256, (int(height * scale) // 8) * 8)
            image = image.resize((width, height), Image.Resampling.LANCZOS)

            prompt = self._prepare_prompt(prompt)
            negative_prompt = self._prepare_prompt(negative_prompt)
            strength = max(0.05, min(float(strength), 0.95))
            steps = max(1, min(int(steps), 60))

            prompt_embeds_data = self._build_prompt_embeddings(
                prompt, negative_prompt
            )

            # Build the matching img2img pipeline from the already-loaded
            # components. This avoids downloading another model.
            if self.model_type == "StableDiffusionPipeline":
                edit_pipe = StableDiffusionImg2ImgPipeline.from_pipe(self.pipe)
            elif self.model_type == "StableDiffusionXLPipeline":
                edit_pipe = StableDiffusionXLImg2ImgPipeline.from_pipe(self.pipe)
            else:
                raise RuntimeError(
                    f"Image-to-image is not supported for {self.model_type}."
                )

            if hasattr(edit_pipe, "vae"):
                if hasattr(edit_pipe.vae, "enable_slicing"):
                    edit_pipe.vae.enable_slicing()
                if hasattr(edit_pipe.vae, "enable_tiling"):
                    edit_pipe.vae.enable_tiling()

            try:
                from diffusers.models.attention_processor import AttnProcessor2_0
                if hasattr(edit_pipe, "unet"):
                    edit_pipe.unet.set_attn_processor(AttnProcessor2_0())
            except Exception:
                pass

            generator = None
            if int(seed) >= 0:
                generator = torch.Generator(
                    device="cuda" if torch.cuda.is_available() else "cpu"
                ).manual_seed(int(seed))

            kwargs = {
                "image": image,
                "strength": strength,
                "num_inference_steps": steps,
                "guidance_scale": float(guidance),
            }

            if self.model_type == "StableDiffusionXLPipeline":
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                    kwargs["pooled_prompt_embeds"],
                    kwargs["negative_pooled_prompt_embeds"],
                ) = prompt_embeds_data
            else:
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                ) = prompt_embeds_data
            if generator is not None:
                kwargs["generator"] = generator

            with self._lock:
                result = edit_pipe(**kwargs).images[0]

            del edit_pipe
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            os.makedirs(config.GENERATED_IMAGES_DIR, exist_ok=True)
            name = f"{uuid.uuid4().hex}.png"
            output_path = os.path.join(config.GENERATED_IMAGES_DIR, name)
            result.save(output_path)

            return "/static/generated/" + name

        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise


    def _decode_image_data(self, image_data, label="image"):
        if not isinstance(image_data, str) or "," not in image_data:
            raise ValueError(f"Valid {label} data is required.")
        try:
            raw = base64.b64decode(image_data.split(",", 1)[1])
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as exc:
            raise ValueError(f"Could not decode {label}: {exc}") from exc

    def _save_result(self, image):
        os.makedirs(config.GENERATED_IMAGES_DIR, exist_ok=True)
        name = f"{uuid.uuid4().hex}.png"
        output_path = os.path.join(config.GENERATED_IMAGES_DIR, name)
        image.save(output_path)
        return "/static/generated/" + name

    def inpaint(
        self,
        prompt,
        negative_prompt="",
        image_data="",
        mask_data="",
        strength=0.75,
        steps=24,
        guidance=5.0,
        seed=-1,
    ):
        """
        Masked inpainting/editing using the currently loaded image model.

        White mask pixels are replaced.
        Black mask pixels are preserved.

        Dedicated SD 1.5 inpainting checkpoints use native inpainting.
        Normal SD 1.5 and SDXL/Pony checkpoints use a localized img2img
        fallback and composite the generated region back onto the original.
        """

        if self.pipe is None:
            raise RuntimeError("No image model loaded.")

        import torch
        from diffusers import (
            StableDiffusionImg2ImgPipeline,
            StableDiffusionXLImg2ImgPipeline,
        )

        image = self._decode_image_data(image_data, "source image")
        mask = self._decode_image_data(mask_data, "mask").convert("L")

        # Make mask exactly the same size as source image.
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.LANCZOS)

        # Make sure something was actually painted.
        bbox = mask.getbbox()
        if not bbox:
            raise ValueError(
                "The mask is empty. Paint the area you want to change."
            )

        prompt = self._prepare_prompt(prompt)
        negative_prompt = self._prepare_prompt(negative_prompt)

        prompt_embeds_data = self._build_prompt_embeddings(
            prompt, negative_prompt
        )

        strength = max(0.05, min(float(strength), 0.98))
        steps = max(1, min(int(steps), 60))
        guidance = float(guidance)

        # Seed
        generator = None
        if int(seed) >= 0:
            generator = torch.Generator(
                device="cuda" if torch.cuda.is_available() else "cpu"
            ).manual_seed(int(seed))

        # ---------------------------------------------------------
        # Native SD 1.5 inpainting checkpoint
        # ---------------------------------------------------------

        if self.model_type == "StableDiffusionInpaintPipeline":

            scale = min(
                1.0,
                1024.0 /
                max(
                    image.width,
                    image.height
                )
            )

            width = max(
                256,
                (int(image.width * scale) // 8) * 8
            )

            height = max(
                256,
                (int(image.height * scale) // 8) * 8
            )

            image = image.resize(
                (width, height),
                Image.Resampling.LANCZOS
            )

            mask = mask.resize(
                (width, height),
                Image.Resampling.LANCZOS
            )

            kwargs = {
                "image": image,
                "mask_image": mask,
                "strength": strength,
                "num_inference_steps": steps,
                "guidance_scale": guidance,
            }

            if self.model_type == "StableDiffusionXLPipeline":
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                    kwargs["pooled_prompt_embeds"],
                    kwargs["negative_pooled_prompt_embeds"],
                ) = prompt_embeds_data
            else:
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                ) = prompt_embeds_data

            if generator is not None:
                kwargs["generator"] = generator

            with self._lock:
                result = self.pipe(
                    **kwargs
                ).images[0]

            return self._save_result(result)

        # ---------------------------------------------------------
        # Normal SD 1.5 OR SDXL/Pony fallback
        # ---------------------------------------------------------

        if self.model_type in (
            "StableDiffusionPipeline",
            "StableDiffusionXLPipeline",
        ):

            left, top, right, bottom = bbox

            # Add surrounding context around the masked area.
            mask_width = right - left
            mask_height = bottom - top

            pad = max(
                48,
                int(
                    max(
                        mask_width,
                        mask_height
                    ) * 0.40
                )
            )

            left = max(
                0,
                left - pad
            )

            top = max(
                0,
                top - pad
            )

            right = min(
                image.width,
                right + pad
            )

            bottom = min(
                image.height,
                bottom + pad
            )

            # Crop source and mask.
            crop = image.crop(
                (
                    left,
                    top,
                    right,
                    bottom
                )
            )

            crop_mask = mask.crop(
                (
                    left,
                    top,
                    right,
                    bottom
                )
            )

            # Keep the crop reasonably sized for the 6 GB GPU.
            max_side = (
                768
                if self.model_type ==
                    "StableDiffusionPipeline"
                else 768
            )

            scale = min(
                1.0,
                max_side /
                max(
                    crop.width,
                    crop.height
                )
            )

            crop_width = max(
                256,
                (int(crop.width * scale) // 8) * 8
            )

            crop_height = max(
                256,
                (int(crop.height * scale) // 8) * 8
            )

            crop = crop.resize(
                (
                    crop_width,
                    crop_height
                ),
                Image.Resampling.LANCZOS
            )

            # Create matching img2img pipeline from the
            # already-loaded model. No second model download.
            if self.model_type == "StableDiffusionPipeline":

                edit_pipe = (
                    StableDiffusionImg2ImgPipeline
                    .from_pipe(self.pipe)
                )

            else:

                edit_pipe = (
                    StableDiffusionXLImg2ImgPipeline
                    .from_pipe(self.pipe)
                )

            # Memory optimizations.
            if hasattr(edit_pipe, "vae"):

                if hasattr(
                    edit_pipe.vae,
                    "enable_slicing"
                ):
                    edit_pipe.vae.enable_slicing()

                if hasattr(
                    edit_pipe.vae,
                    "enable_tiling"
                ):
                    edit_pipe.vae.enable_tiling()

            try:
                from diffusers.models.attention_processor import (
                    AttnProcessor2_0
                )

                if hasattr(
                    edit_pipe,
                    "unet"
                ):
                    edit_pipe.unet.set_attn_processor(
                        AttnProcessor2_0()
                    )

            except Exception:
                pass

            kwargs = {
                "image": crop,
                "strength": strength,
                "num_inference_steps": steps,
                "guidance_scale": guidance,
            }

            if self.model_type == "StableDiffusionXLPipeline":
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                    kwargs["pooled_prompt_embeds"],
                    kwargs["negative_pooled_prompt_embeds"],
                ) = prompt_embeds_data
            else:
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                ) = prompt_embeds_data

            if generator is not None:
                kwargs["generator"] = generator

            # Generate replacement crop.
            with self._lock:

                generated = edit_pipe(
                    **kwargs
                ).images[0]

            # Release temporary pipeline.
            del edit_pipe

            if torch.cuda.is_available():

                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

            # Return generated image to original crop size.
            target_size = (
                right - left,
                bottom - top
            )

            generated = generated.resize(
                target_size,
                Image.Resampling.LANCZOS
            )

            crop_mask = crop_mask.resize(
                target_size,
                Image.Resampling.LANCZOS
            )

            # Composite ONLY the painted region.
            result = image.copy()

            result.paste(
                generated,
                (
                    left,
                    top
                ),
                crop_mask
            )

            return self._save_result(result)

        # ---------------------------------------------------------
        # Unsupported pipeline
        # ---------------------------------------------------------

        raise RuntimeError(
            f"Inpainting is not supported for "
            f"{self.model_type}."
        )

    def generate(
        self,
        prompt,
        negative_prompt="",
        width=512,
        height=512,
        steps=24,
        guidance=5.0,
        seed=-1,
    ):
        if self.pipe is None:
            raise RuntimeError("No image model loaded.")

        width = max(256, min(int(width), 2048))
        height = max(256, min(int(height), 2048))
        steps = max(1, min(int(steps), 60))

        # SD 1.5 attention can become extremely memory-hungry at SDXL-sized
        # resolutions. On a 6 GB GPU, keep Realistic Vision in a practical
        # range. Users can still request portrait 768x1024 or similar.
        if self.model_type == "StableDiffusionPipeline":
            width = min(width, 1024)
            height = min(height, 1024)

        width = (width // 8) * 8
        height = (height // 8) * 8

        try:
            import torch

            # Reduce CUDA allocator fragmentation on long-running local use.
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

            # Build embeddings with Compel so long prompts are chunked
            # instead of truncated at CLIP's normal 77-token limit.
            prompt = self._prepare_prompt(prompt)
            negative_prompt = self._prepare_prompt(negative_prompt)
            prompt_embeds_data = self._build_prompt_embeddings(
                prompt, negative_prompt
            )

            generator = None

            if int(seed) >= 0:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                generator = torch.Generator(device=device).manual_seed(int(seed))

            kwargs = dict(
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=float(guidance),
            )

            if self.model_type == "StableDiffusionXLPipeline":
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                    kwargs["pooled_prompt_embeds"],
                    kwargs["negative_pooled_prompt_embeds"],
                ) = prompt_embeds_data
            else:
                (
                    kwargs["prompt_embeds"],
                    kwargs["negative_prompt_embeds"],
                ) = prompt_embeds_data

            if generator is not None:
                kwargs["generator"] = generator

            # _build_prompt_embeddings() already validates the tokenizer
            # and text encoder before inference.
            with self._lock:
                image = self.pipe(**kwargs).images[0]

            os.makedirs(config.GENERATED_IMAGES_DIR, exist_ok=True)

            name = f"{uuid.uuid4().hex}.png"
            output_path = os.path.join(config.GENERATED_IMAGES_DIR, name)
            image.save(output_path)

            return "/static/generated/" + name

        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise


image_engine = ImageEngine()
