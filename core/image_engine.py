"""Local diffusion image engine with RTX 3050-friendly profiles, schedulers,
LoRAs, hires refinement, img2img and runtime diagnostics."""
import base64, gc, io, os, threading, time, uuid
from PIL import Image, ImageFilter
import config

MODEL_PROFILES = {
    "sdxl": {
        "family": "SDXL",
        "default_width": 1024, "default_height": 576,
        "fast_steps": 18, "balanced_steps": 28, "high_steps": 36,
        "guidance": 5.5, "max_pixels": 1048576,
        "sampler": "DPM++ 2M Karras",
    },
    "pony": {
        "family": "Pony/SDXL",
        "default_width": 1024, "default_height": 576,
        "fast_steps": 18, "balanced_steps": 28, "high_steps": 36,
        "guidance": 6.0, "max_pixels": 1048576,
        "sampler": "DPM++ 2M Karras",
    },
    "sd15": {
        "family": "SD 1.5",
        "default_width": 768, "default_height": 512,
        "fast_steps": 16, "balanced_steps": 24, "high_steps": 32,
        "guidance": 6.0, "max_pixels": 786432,
        "sampler": "DPM++ 2M Karras",
    },
}

ANATOMY_NEGATIVE_BASE = (
    "bad anatomy, deformed anatomy, malformed hands, extra fingers, missing fingers, "
    "fused fingers, extra limbs, missing limbs, duplicated body parts, malformed feet, "
    "distorted face, asymmetrical eyes, warped body, bad proportions, disfigured, "
    "duplicate person, cloned face, unnatural pose, broken joints, twisted limbs"
)

QUALITY_NEGATIVE_BASE = "blurry, low quality, low detail, jpeg artifacts, watermark, text, logo, oversharpened"

STYLE_PRESETS = {
    "photorealistic": "photorealistic, natural skin texture, realistic materials, physically plausible lighting",
    "cinematic": "cinematic photography, dramatic composition, realistic lighting, subtle film grain, cinematic color grade",
    "editorial": "high-end editorial photography, polished composition, controlled studio-quality lighting",
    "digital_illustration": "high-quality digital illustration, clean rendering, detailed forms, polished artwork",
    "pencil_drawing": "detailed graphite pencil drawing, hand-drawn linework, realistic shading, paper texture",
    "watercolor": "detailed watercolor painting, natural brushwork, translucent washes, textured paper",
    "comic": "detailed comic-book artwork, clean ink lines, controlled shading, dynamic composition",
    "anime_inspired": "anime-inspired illustration, clean line art, expressive eyes, cel shading, detailed character design",
    "fantasy_art": "high-detail fantasy concept art, atmospheric environment, painterly detail, dramatic lighting",
}

EDIT_PRESETS = {
    "general": (0.40, 26, 5.0),
    "background": (0.46, 28, 5.0),
    "clothing": (0.38, 28, 5.0),
    "relight": (0.28, 24, 4.8),
    "restyle": (0.52, 28, 5.2),
    "full_body": (0.62, 30, 5.2),
}

def apply_style_prompt(prompt, style=""):
    style_key=str(style or "").strip().lower()
    prefix=STYLE_PRESETS.get(style_key, "")
    if not prefix: return str(prompt).strip()
    text=str(prompt).strip()
    if prefix.lower() in text.lower(): return text
    return f"{prefix}, {text}" if text else prefix


def merge_negative_prompt(user_negative, character_mode=False):
    parts=[]
    if user_negative and str(user_negative).strip(): parts.append(str(user_negative).strip())
    parts.append(ANATOMY_NEGATIVE_BASE)
    parts.append(QUALITY_NEGATIVE_BASE)
    if character_mode:
        parts.append("duplicate character, inconsistent facial features, inconsistent hair, changing identity")
    seen=set(); out=[]
    for part in ", ".join(parts).split(","):
        item=part.strip()
        key=item.lower()
        if item and key not in seen:
            seen.add(key); out.append(item)
    return ", ".join(out)

SCHEDULERS = {
    "DPM++ 2M Karras": ("DPMSolverMultistepScheduler", {"algorithm_type": "dpmsolver++", "use_karras_sigmas": True}),
    "DPM++ SDE Karras": ("DPMSolverMultistepScheduler", {"algorithm_type": "sde-dpmsolver++", "use_karras_sigmas": True}),
    "Euler A": ("EulerAncestralDiscreteScheduler", {}),
    "Euler": ("EulerDiscreteScheduler", {}),
    "DDIM": ("DDIMScheduler", {}),
    "UniPC": ("UniPCMultistepScheduler", {}),
}

class ImageEngine:
    def __init__(self):
        self.pipe=None; self.model_path=None; self.model_type=None
        self.model_family=""; self.error=""; self._lock=threading.Lock()
        self.inpaint_pipe=None; self.inpaint_model_path=None; self.inpaint_model_type=None
        self.faceid_pipe=None; self.faceid_model_path=None; self.faceid_family=""
        self.loaded_loras=[]; self.current_scheduler="DPM++ 2M Karras"

    @property
    def available(self):
        try:
            import torch, diffusers
            return True
        except Exception as e:
            self.error=f"{type(e).__name__}: {e}"; return False

    def list_models(self):
        # Only expose normal text-to-image checkpoints/directories here.
        # Dedicated pipelines such as image_models\inpainting are loaded by
        # their own endpoint and must never be passed to AutoPipelineForText2Image.
        os.makedirs(config.IMAGE_MODELS_DIR,exist_ok=True)
        out=[]
        for n in os.listdir(config.IMAGE_MODELS_DIR):
            if n.startswith("."):
                continue
            p=os.path.join(config.IMAGE_MODELS_DIR,n)
            if os.path.isdir(p) and n.lower() == "inpainting":
                continue
            if os.path.isdir(p) or n.lower().endswith((".safetensors",".ckpt")):
                out.append(n)
        return sorted(out)

    def list_loras(self):
        root=config.LORA_MODELS_DIR
        os.makedirs(root,exist_ok=True)
        return sorted([n for n in os.listdir(root) if n.lower().endswith((".safetensors",".ckpt"))])

    def _safe_model_path(self,name,root):
        if not name: raise ValueError("model name is required")
        base=os.path.realpath(root); path=os.path.realpath(os.path.join(root,os.path.basename(name)))
        if os.path.commonpath([base,path])!=base: raise ValueError("Invalid model path")
        if not (os.path.isfile(path) or os.path.isdir(path)): raise FileNotFoundError(path)
        return path

    def _profile_for(self,name=None):
        n=(name or self.model_path or "").lower()
        if any(x in n for x in ("realisticvision","realistic_vision","realistic-vision","v60b1","v51vae","v5.1vae")): return MODEL_PROFILES["sd15"]
        if "pony" in n: return MODEL_PROFILES["pony"]
        return MODEL_PROFILES["sdxl"] if "xl" in n or "realvis" in n or "juggernaut" in n else MODEL_PROFILES["sdxl"]

    def profile(self):
        p=dict(self._profile_for())
        p["loaded_model"]=os.path.basename(self.model_path) if self.model_path else ""
        p["model_type"]=self.model_type or ""
        p["model_family"]=self.model_family or p["family"]
        p["samplers"]=list(SCHEDULERS)
        return p

    def _unload_current(self):
        if self.pipe is not None:
            try: del self.pipe
            except Exception: pass
        self.pipe=None; self.model_path=None; self.model_type=None; self.model_family=""; self.loaded_loras=[]
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available(): torch.cuda.empty_cache(); torch.cuda.ipc_collect()
        except Exception: pass

    def unload(self):
        with self._lock:
            self._unload_current(); self.error=""

    def load(self,name):
        path=self._safe_model_path(name,config.IMAGE_MODELS_DIR)
        # Prevent the normal generation loader from ever trying to interpret
        # the dedicated inpainting directory as a Diffusers model.
        if os.path.isdir(path) and os.path.basename(os.path.normpath(path)).lower() == "inpainting":
            raise ValueError("The inpainting model is managed by the Inpaint tab. Use /api/images/inpaint instead of loading the inpainting folder as a normal model.")
        try:
            import torch
            from diffusers import AutoPipelineForText2Image, StableDiffusionXLPipeline, StableDiffusionPipeline
        except Exception as e:
            raise RuntimeError("Install image backend: pip install torch diffusers transformers accelerate safetensors Pillow") from e
        try:
            from core.llm_engine import engine as text_engine; text_engine.unload_model()
        except Exception: pass
        with self._lock:
            self._unload_current()
            dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            if os.path.isfile(path):
                low=os.path.basename(path).lower()
                is_sd15=any(x in low for x in ("realisticvision","realistic_vision","realistic-vision","v60b1","v5.1vae","v51vae"))
                if is_sd15:
                    pipe=StableDiffusionPipeline.from_single_file(path,torch_dtype=dtype,local_files_only=True,use_safetensors=path.lower().endswith(".safetensors"))
                else:
                    pipe=StableDiffusionXLPipeline.from_single_file(path,torch_dtype=dtype,local_files_only=True,use_safetensors=path.lower().endswith(".safetensors"))
            else:
                pipe=AutoPipelineForText2Image.from_pretrained(path,torch_dtype=dtype,local_files_only=True)
            if hasattr(pipe,"vae"):
                if hasattr(pipe.vae,"enable_slicing"): pipe.vae.enable_slicing()
                if hasattr(pipe.vae,"enable_tiling"): pipe.vae.enable_tiling()
            try:
                from diffusers.models.attention_processor import AttnProcessor2_0
                if hasattr(pipe,"unet"): pipe.unet.set_attn_processor(AttnProcessor2_0())
            except Exception: pass
            if torch.cuda.is_available():
                if hasattr(pipe,"enable_sequential_cpu_offload"): pipe.enable_sequential_cpu_offload()
                else: pipe.enable_model_cpu_offload()
            else: pipe.to("cpu")
            self.pipe=pipe; self.model_path=path; self.model_type=type(pipe).__name__
            self.model_family=self._profile_for(path)["family"]; self.error=""
            self.set_scheduler(self._profile_for(path)["sampler"])
        return path

    def set_scheduler(self,name):
        if not self.pipe: return
        if name not in SCHEDULERS: raise ValueError(f"Unknown scheduler: {name}")
        clsname,kwargs=SCHEDULERS[name]
        try:
            import diffusers
            cls=getattr(diffusers,clsname)
            cfg=self.pipe.scheduler.config
            self.pipe.scheduler=cls.from_config(cfg,**kwargs)
            self.current_scheduler=name
        except Exception as e:
            raise RuntimeError(f"Could not set sampler {name}: {e}")

    def _truncate_for_tokenizer(self,text,tokenizer):
        if not text or tokenizer is None: return text
        max_length=getattr(tokenizer,"model_max_length",77)
        if not isinstance(max_length,int) or max_length<=0 or max_length>4096: max_length=77
        try: encoded=tokenizer(text,truncation=True,max_length=max_length,padding=False,return_tensors=None)
        except Exception: return text
        ids=encoded.get("input_ids") if isinstance(encoded,dict) else None
        if ids is None: return text
        if ids and isinstance(ids[0],(list,tuple)): ids=list(ids[0])
        else: ids=list(ids)
        if len(ids)<=max_length: return text
        return tokenizer.decode(ids[:max_length],skip_special_tokens=True,clean_up_tokenization_spaces=True)

    def _prepare_prompt(self,text):
        if not text or not self.pipe: return text
        toks=[]
        for attr in ("tokenizer","tokenizer_2"):
            tok=getattr(self.pipe,attr,None)
            if tok is not None and hasattr(tok,"tokenize") and tok not in toks: toks.append(tok)
        result=text
        for tok in toks: result=self._truncate_for_tokenizer(result,tok)
        return result

    def token_info(self,text):
        if not self.pipe: return {"tokens":0,"limit":77,"truncated":False}
        toks=[]
        for attr in ("tokenizer","tokenizer_2"):
            tok=getattr(self.pipe,attr,None)
            if tok is not None and tok not in toks: toks.append(tok)
        counts=[]; limits=[]
        for tok in toks:
            try:
                ids=tok(text,add_special_tokens=True).get("input_ids",[])
                if ids and isinstance(ids[0],list): ids=ids[0]
                counts.append(len(ids)); limits.append(int(getattr(tok,"model_max_length",77)))
            except Exception: pass
        return {"tokens":max(counts or [0]),"limit":min(limits or [77]),"truncated":bool(counts and any(c>l for c,l in zip(counts,limits)))}

    def _normalize_dimensions(self,width,height,quality="balanced"):
        p=self._profile_for(); width=max(256,min(int(width),2048)); height=max(256,min(int(height),2048))
        budget=p["max_pixels"]
        if quality=="fast": budget=min(budget,786432)
        elif quality=="high": budget=min(budget,1048576)
        if width*height>budget:
            scale=(budget/(width*height))**0.5; width=int(width*scale); height=int(height*scale)
        width=max(256,(width//8)*8); height=max(256,(height//8)*8)
        return width,height

    def _adapter_names_present(self):
        """Return adapter names actually registered by Diffusers/PEFT."""
        if not self.pipe:
            return set()
        names=set()
        try:
            getter=getattr(self.pipe,"get_list_adapters",None)
            if callable(getter):
                data=getter()
                if isinstance(data,dict):
                    for vals in data.values():
                        if isinstance(vals,(list,tuple,set)):
                            names.update(str(v) for v in vals)
                elif isinstance(data,(list,tuple,set)):
                    names.update(str(v) for v in data)
        except Exception:
            pass
        # Some Diffusers versions expose adapters directly on the UNet/text encoders.
        for obj_name in ("unet","transformer","text_encoder","text_encoder_2"):
            obj=getattr(self.pipe,obj_name,None)
            if obj is None: continue
            try:
                getter=getattr(obj,"get_list_adapters",None)
                if callable(getter):
                    data=getter()
                    if isinstance(data,dict):
                        for vals in data.values():
                            if isinstance(vals,(list,tuple,set)):
                                names.update(str(v) for v in vals)
                    elif isinstance(data,(list,tuple,set)):
                        names.update(str(v) for v in data)
            except Exception:
                pass
        return names

    def load_loras(self,loras):
        """Load only adapters compatible with the currently loaded pipeline.

        Civitai/Hugging Face folders often contain LoRAs for different model
        families. Diffusers can emit warnings and leave no adapter registered
        when a LoRA does not match the loaded UNet/text encoders. Never call
        set_adapters() with such names because that produces the opaque
        'adapter name ... not in the list of present adapters' error.
        """
        if not self.pipe:
            return
        loras=loras or []
        if isinstance(loras,str):
            loras=[x.strip() for x in loras.split(",") if x.strip()]

        # Remove adapters from the previous generation first.
        if self.loaded_loras and hasattr(self.pipe,"unload_lora_weights"):
            try: self.pipe.unload_lora_weights()
            except Exception: pass
        self.loaded_loras=[]

        valid=[]
        for item in loras:
            if isinstance(item,str):
                name=item; weight=0.7
            else:
                name=item.get("name"); weight=float(item.get("weight",0.7))
            if not name: continue
            path=self._safe_model_path(name,config.LORA_MODELS_DIR)
            valid.append((path,max(0.0,min(float(weight),2.0))))

        if not valid:
            return
        if not hasattr(self.pipe,"load_lora_weights"):
            raise RuntimeError("This image pipeline does not support LoRA adapters.")

        adapters=[]
        skipped=[]
        for idx,(path,weight) in enumerate(valid):
            adapter=f"newair_{idx}_{uuid.uuid4().hex[:6]}"
            try:
                self.pipe.load_lora_weights(path,adapter_name=adapter)
                present=self._adapter_names_present()
                if adapter not in present:
                    skipped.append(os.path.basename(path))
                    # A partially injected adapter can exist on some versions.
                    try:
                        if hasattr(self.pipe,"unload_lora_weights"):
                            self.pipe.unload_lora_weights()
                    except Exception: pass
                    # Re-load already accepted adapters after a failed attempt.
                    if adapters:
                        rebuilt=[]
                        for old_path,old_weight,old_name in adapters:
                            old_adapter=f"newair_keep_{uuid.uuid4().hex[:6]}"
                            try:
                                self.pipe.load_lora_weights(old_path,adapter_name=old_adapter)
                                if old_adapter in self._adapter_names_present():
                                    rebuilt.append((old_adapter,old_weight,old_name))
                            except Exception: pass
                        adapters=rebuilt
                    continue
                adapters.append((adapter,weight,os.path.basename(path)))
            except Exception as e:
                skipped.append(f"{os.path.basename(path)} ({e})")

        if not adapters:
            if skipped:
                family=self.model_family or self._profile_for().get("family","unknown")
                raise RuntimeError(
                    "None of the selected LoRAs are compatible with the loaded "
                    f"{family} model. Skipped: {', '.join(skipped)}. "
                    "Use an LoRA trained for the same model family (SDXL/SD1.5/Pony)."
                )
            return

        names=[a[0] for a in adapters]
        weights=[a[1] for a in adapters]
        present=self._adapter_names_present()
        names=[n for n in names if n in present]
        if not names:
            raise RuntimeError("The selected LoRA adapters were not registered by Diffusers/PEFT.")
        weights=weights[:len(names)]
        self.pipe.set_adapters(names,adapter_weights=weights)
        by_name={a[0]:a for a in adapters}
        self.loaded_loras=[{"name":by_name[n][2],"weight":by_name[n][1]} for n in names]
        if skipped:
            self.error="Skipped incompatible LoRAs: "+", ".join(skipped)
        else:
            self.error=""

    def _generator(self,seed):
        if int(seed)<0: return None
        import torch
        return torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(int(seed))

    def _common_kwargs(self,prompt,negative_prompt,steps,guidance,generator):
        k={"prompt":self._prepare_prompt(prompt),"negative_prompt":self._prepare_prompt(negative_prompt or "") or None,"num_inference_steps":steps,"guidance_scale":float(guidance)}
        if generator is not None: k["generator"]=generator
        return k

    def generate(self,prompt,negative_prompt="",width=1024,height=576,steps=28,guidance=5.5,seed=-1,sampler="DPM++ 2M Karras",quality="balanced",loras=None,hires=False,hires_scale=1.5,hires_denoise=0.35,character_mode=False,style=""):
        if self.pipe is None: raise RuntimeError("No image model loaded.")
        started=time.time(); width,height=self._normalize_dimensions(width,height,quality); steps=max(1,min(int(steps),60)); guidance=float(guidance)
        self.set_scheduler(sampler)
        self.load_loras(loras)
        prompt=apply_style_prompt(str(prompt).strip(),style)
        if character_mode:
            prompt=("coherent human anatomy, natural body proportions, physically plausible pose, "
                    "clear facial structure, realistic hands and feet, consistent primary character, " + prompt)
        negative_prompt=self._prepare_prompt(merge_negative_prompt(negative_prompt, character_mode))
        guidance=max(3.5,min(float(guidance),8.0))
        if getattr(self.pipe,"tokenizer",None) is None: raise RuntimeError("Loaded checkpoint has no tokenizer. Check that it is a compatible SD checkpoint.")
        if int(seed)<0:
            import secrets
            seed=secrets.randbelow(2147483646)+1
        generator=self._generator(seed)
        kwargs=self._common_kwargs(prompt,negative_prompt,steps,guidance,generator); kwargs.update(width=width,height=height)
        with self._lock: image=self.pipe(**kwargs).images[0]
        if hires:
            image=self._hires_pass(image,prompt,negative_prompt,steps, guidance, seed, hires_scale,hires_denoise)
        os.makedirs(config.GENERATED_IMAGES_DIR,exist_ok=True); name=f"{uuid.uuid4().hex}.png"; image.save(os.path.join(config.GENERATED_IMAGES_DIR,name))
        return {"url":"/static/generated/"+name,"width":image.width,"height":image.height,"seed":int(seed),"sampler":self.current_scheduler,"generation_ms":int((time.time()-started)*1000),"loras":self.loaded_loras.copy(),"model":os.path.basename(self.model_path or ""),"model_family":self.model_family}

    def _hires_pass(self,image,prompt,negative_prompt,steps,guidance,seed,scale,denoise):
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline,StableDiffusionXLImg2ImgPipeline
        scale=max(1.15,min(float(scale),1.75)); denoise=max(0.15,min(float(denoise),0.45))
        max_pixels=self._profile_for()["max_pixels"]*2
        w=min(int(image.width*scale),2048); h=min(int(image.height*scale),2048)
        if w*h>max_pixels:
            s=(max_pixels/(w*h))**0.5; w=int(w*s); h=int(h*s)
        w=max(256,(w//8)*8); h=max(256,(h//8)*8); image=image.resize((w,h),Image.Resampling.LANCZOS)
        cls=StableDiffusionImg2ImgPipeline if self.model_type=="StableDiffusionPipeline" else StableDiffusionXLImg2ImgPipeline
        edit=cls.from_pipe(self.pipe)
        if hasattr(edit,"vae"):
            if hasattr(edit.vae,"enable_slicing"): edit.vae.enable_slicing()
            if hasattr(edit.vae,"enable_tiling"): edit.vae.enable_tiling()
        g=self._generator(seed)
        k=self._common_kwargs(prompt,negative_prompt,max(8,min(steps,50)),guidance,g)
        k.update(image=image,strength=denoise)
        with self._lock: out=edit(**k).images[0]
        del edit
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        return out

    def img2img(self,prompt,negative_prompt="",image_data="",strength=0.55,steps=20,guidance=5.0,seed=-1,sampler="DPM++ 2M Karras",loras=None,style="",edit_mode="general"):
        if self.pipe is None: raise RuntimeError("No image model loaded.")
        if not image_data or "," not in image_data: raise ValueError("Valid image data is required.")
        try:
            raw=base64.b64decode(image_data.split(",",1)[1],validate=True)
            image=Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception as e:
            raise ValueError(f"Could not decode source image: {e}") from e
        width,height=self._normalize_dimensions(image.width,image.height,"balanced")
        # Use 64-pixel multiples for img2img. This avoids empty latent/attention
        # tensors in some SDXL + Accelerate offload combinations.
        width=max(512,(width//64)*64); height=max(512,(height//64)*64)
        p=self._profile_for(); max_pixels=int(p["max_pixels"])
        if width*height>max_pixels:
            scale=(max_pixels/(width*height))**0.5
            width=max(512,int(width*scale)//64*64)
            height=max(512,int(height*scale)//64*64)
        image=image.resize((width,height),Image.Resampling.LANCZOS)
        import torch
        from diffusers import StableDiffusionImg2ImgPipeline,StableDiffusionXLImg2ImgPipeline
        self.set_scheduler(sampler)
        self.load_loras(loras or [])
        preset=EDIT_PRESETS.get(str(edit_mode or "general"),EDIT_PRESETS["general"])
        if strength is None: strength=preset[0]
        prompt=apply_style_prompt(prompt,style)
        cls=StableDiffusionImg2ImgPipeline if self.model_type=="StableDiffusionPipeline" else StableDiffusionXLImg2ImgPipeline
        strength=max(.05,min(float(strength),.95)); steps=max(1,min(int(steps),60))
        # Build a fresh img2img wrapper from shared components. from_pipe() can
        # retain stale Accelerate offload hooks and yield an empty attention tensor.
        try:
            edit=cls(**dict(self.pipe.components))
        except Exception:
            edit=cls.from_pipe(self.pipe)
        if hasattr(edit,"vae"):
            if hasattr(edit.vae,"enable_slicing"): edit.vae.enable_slicing()
            if hasattr(edit.vae,"enable_tiling"): edit.vae.enable_tiling()
        try:
            from diffusers.models.attention_processor import AttnProcessor2_0
            if hasattr(edit,"unet"): edit.unet.set_attn_processor(AttnProcessor2_0())
        except Exception: pass
        if self.loaded_loras:
            names=[x["name"] for x in self.loaded_loras]; weights=[x["weight"] for x in self.loaded_loras]
            try: edit.set_adapters(names,adapter_weights=weights)
            except Exception: pass
        k=self._common_kwargs(prompt,negative_prompt,steps,guidance,self._generator(seed)); k.update(image=image,strength=strength)
        try:
            with self._lock: result=edit(**k).images[0]
        except RuntimeError as e:
            msg=str(e)
            if "reshape tensor of 0 elements" in msg or "specified dimension -1" in msg:
                raise RuntimeError(f"Img2img produced an empty latent tensor at {width}x{height}. Reload the image model and retry with strength 0.45-0.75 and 20-30 steps.") from e
            raise
        finally:
            del edit
            if torch.cuda.is_available(): torch.cuda.empty_cache()
        os.makedirs(config.GENERATED_IMAGES_DIR,exist_ok=True); name=f"{uuid.uuid4().hex}.png"; result.save(os.path.join(config.GENERATED_IMAGES_DIR,name))
        return {"url":"/static/generated/"+name,"width":result.width,"height":result.height,"seed":int(seed),"sampler":self.current_scheduler,"generation_ms":0,"loras":self.loaded_loras.copy(),"model":os.path.basename(self.model_path or ""),"model_family":self.model_family}

    def _find_inpaint_model(self):
        roots=[getattr(config,"INPAINT_MODELS_DIR",os.path.join(config.IMAGE_MODELS_DIR,"inpainting")), config.IMAGE_MODELS_DIR]
        preferred=("sd-v1-5-inpainting.ckpt","sd-v1-5-inpaint.ckpt","stable-diffusion-inpainting.ckpt")
        for root in roots:
            if not os.path.isdir(root):
                continue
            for name in preferred:
                path=os.path.join(root,name)
                if os.path.isfile(path): return path
            for name in sorted(os.listdir(root)):
                if "inpaint" in name.lower() and name.lower().endswith((".ckpt",".safetensors",".bin")):
                    return os.path.join(root,name)
        return ""

    def inpaint_status(self):
        path=self._find_inpaint_model()
        return {"available":bool(path),"path":path,"model":os.path.basename(path) if path else "",
                "loaded":bool(self.inpaint_pipe is not None),"error":self.error if self.inpaint_pipe is None else ""}

    def _unload_inpaint(self):
        if self.inpaint_pipe is not None:
            try: del self.inpaint_pipe
            except Exception: pass
        self.inpaint_pipe=None; self.inpaint_model_path=None; self.inpaint_model_type=None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available(): torch.cuda.empty_cache(); torch.cuda.ipc_collect()
        except Exception: pass

    def load_inpaint(self):
        path=self._find_inpaint_model()
        if not path:
            raise FileNotFoundError(
                "Stable Diffusion v1.5 inpainting checkpoint not found. Put "
                "sd-v1-5-inpainting.ckpt in image_models\\inpainting."
            )
        if self.inpaint_pipe is not None and os.path.realpath(self.inpaint_model_path or "") == os.path.realpath(path):
            return path
        try:
            import torch
            from diffusers import StableDiffusionInpaintPipeline
        except Exception as e:
            raise RuntimeError("Install image backend: pip install -U diffusers transformers accelerate safetensors Pillow") from e
        try:
            from core.llm_engine import engine as text_engine; text_engine.unload_model()
        except Exception: pass

        # SD 1.5 .ckpt files contain the CLIP text encoder weights, but modern
        # Diffusers still needs the CLIP tokenizer/config when converting the
        # checkpoint. On a fully local install that config may not be in the
        # Hugging Face cache. Reuse the tokenizer + text encoder from the
        # already-supported Realistic Vision SD1.5 pipeline when available;
        # otherwise bootstrap them by loading that local checkpoint once.
        shared_text_encoder = None
        shared_tokenizer = None
        with self._lock:
            shared_pipe = self.pipe
            if shared_pipe is not None and self._profile_for(self.model_path).get("family") == "SD 1.5":
                shared_text_encoder = getattr(shared_pipe, "text_encoder", None)
                shared_tokenizer = getattr(shared_pipe, "tokenizer", None)

        if shared_text_encoder is None or shared_tokenizer is None:
            rv_name = None
            for candidate in self.list_models():
                if any(x in candidate.lower() for x in ("realisticvision", "realistic_vision", "realistic-vision", "v60b1", "v51vae", "v5.1vae")):
                    rv_name = candidate
                    break
            if rv_name:
                try:
                    self.load(rv_name)
                    with self._lock:
                        shared_text_encoder = getattr(self.pipe, "text_encoder", None)
                        shared_tokenizer = getattr(self.pipe, "tokenizer", None)
                except Exception as bootstrap_error:
                    raise RuntimeError(
                        "The inpainting checkpoint needs the SD 1.5 CLIP tokenizer/config. "
                        "newAIr tried to bootstrap it from your local Realistic Vision model but failed: "
                        f"{bootstrap_error}"
                    ) from bootstrap_error

        if shared_text_encoder is None or shared_tokenizer is None:
            raise RuntimeError(
                "Could not obtain the local SD 1.5 CLIP tokenizer/text encoder. "
                "Load your Realistic Vision V6 model once, then retry Inpaint."
            )

        with self._lock:
            self._unload_current()
            self._unload_inpaint()
            dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            kwargs={"torch_dtype":dtype,"local_files_only":True,
                    "text_encoder":shared_text_encoder,"tokenizer":shared_tokenizer}
            cfg_path=os.path.join(os.path.dirname(path),"v1-inpainting-inference.yaml")
            if os.path.isfile(cfg_path): kwargs["original_config_file"]=cfg_path
            if path.lower().endswith((".safetensors",".ckpt")):
                try:
                    pipe=StableDiffusionInpaintPipeline.from_single_file(path,**kwargs,use_safetensors=path.lower().endswith(".safetensors"))
                except TypeError:
                    kwargs.pop("use_safetensors",None)
                    pipe=StableDiffusionInpaintPipeline.from_single_file(path,**kwargs)
            else:
                pipe=StableDiffusionInpaintPipeline.from_pretrained(path,**kwargs)
            if hasattr(pipe,"vae"):
                if hasattr(pipe.vae,"enable_slicing"): pipe.vae.enable_slicing()
                if hasattr(pipe.vae,"enable_tiling"): pipe.vae.enable_tiling()
            try:
                from diffusers.models.attention_processor import AttnProcessor2_0
                if hasattr(pipe,"unet"): pipe.unet.set_attn_processor(AttnProcessor2_0())
            except Exception: pass
            if torch.cuda.is_available():
                if hasattr(pipe,"enable_sequential_cpu_offload"): pipe.enable_sequential_cpu_offload()
                else: pipe.enable_model_cpu_offload()
            else: pipe.to("cpu")
            self.inpaint_pipe=pipe; self.inpaint_model_path=path; self.inpaint_model_type=type(pipe).__name__
            try:
                cfg=pipe.scheduler.config
                import diffusers
                pipe.scheduler=diffusers.DPMSolverMultistepScheduler.from_config(cfg,algorithm_type="dpmsolver++",use_karras_sigmas=True)
            except Exception: pass
            self.error=""
        return path

    def inpaint(self,prompt,negative_prompt,image_data,mask_data,steps=30,guidance=5.5,seed=-1,sampler="DPM++ 2M Karras",padding=96,feather=4,mask_expand=8):
        """High-precision masked editing with exact source-pixel preservation.

        The model gets an expanded context mask so it can rebuild clean edges,
        but the final result is composited with the user's original mask in the
        ORIGINAL image coordinates. This prevents crop-resize seams and stops
        unmasked regions from drifting.
        """
        if not image_data or "," not in image_data: raise ValueError("Valid source image data is required.")
        if not mask_data or "," not in mask_data: raise ValueError("A painted mask is required.")
        self.load_inpaint()
        import torch
        try:
            raw=base64.b64decode(image_data.split(",",1)[1],validate=True); src=Image.open(io.BytesIO(raw)).convert("RGB")
            rawm=base64.b64decode(mask_data.split(",",1)[1],validate=True); user_mask=Image.open(io.BytesIO(rawm)).convert("L")
        except Exception as e: raise ValueError(f"Could not decode source or mask: {e}") from e
        if user_mask.size != src.size:
            user_mask=user_mask.resize(src.size,Image.Resampling.NEAREST)

        # Browser masks are treated as binary intent: white = edit, black = preserve.
        user_mask=user_mask.point(lambda p: 255 if p >= 16 else 0)
        bbox=user_mask.getbbox()
        if not bbox: raise ValueError("Paint an area to edit before generating.")

        # Two masks are intentional. The expanded inference mask gives the model
        # room to rebuild boundaries. The final composite mask remains faithful to
        # what the user painted, with only a controlled feather for blending.
        expand=max(0,min(int(mask_expand),48))
        inference_mask=user_mask
        if expand:
            try: inference_mask=inference_mask.filter(ImageFilter.MaxFilter(expand*2+1))
            except Exception: pass

        pad=max(0,min(int(padding),512))
        ibox=inference_mask.getbbox() or bbox
        l=max(0,ibox[0]-pad); t=max(0,ibox[1]-pad); r=min(src.width,ibox[2]+pad); b=min(src.height,ibox[3]+pad)
        if r-l < 64 or b-t < 64:
            cx=(l+r)//2; cy=(t+b)//2; half=max(32,max(r-l,b-t)//2)
            l=max(0,cx-half); r=min(src.width,cx+half); t=max(0,cy-half); b=min(src.height,cy+half)

        crop_box=(l,t,r,b)
        original_crop_size=(r-l,b-t)
        crop=src.crop(crop_box)
        inference_crop_mask=inference_mask.crop(crop_box)
        composite_crop_mask=user_mask.crop(crop_box)
        final_feather=max(0,min(int(feather),24))
        if final_feather:
            composite_crop_mask=composite_crop_mask.filter(ImageFilter.GaussianBlur(final_feather))

        # Preserve aspect ratio. Work at a SD1.5-friendly size, but never paste
        # this resized working image directly into the source. It is always mapped
        # back to original_crop_size first.
        max_side=768; min_side=384
        ow,oh=original_crop_size
        scale=min(max_side/max(ow,oh),1.0)
        if max(ow,oh) < min_side:
            scale=min(min_side/max(ow,oh),1.5)
        ww=max(64,int(round(ow*scale/64))*64); wh=max(64,int(round(oh*scale/64))*64)
        while ww*wh > 589824:
            if ww >= wh: ww-=64
            else: wh-=64
        ww=max(64,ww); wh=max(64,wh)
        work=crop.resize((ww,wh),Image.Resampling.LANCZOS)
        work_mask=inference_crop_mask.resize((ww,wh),Image.Resampling.NEAREST)

        steps=max(16,min(int(steps),50)); guidance=max(3.5,min(float(guidance),7.0))
        try:
            clsname,kwargs=SCHEDULERS.get(sampler,SCHEDULERS["DPM++ 2M Karras"])
            cls=getattr(__import__('diffusers'),clsname)
            self.inpaint_pipe.scheduler=cls.from_config(self.inpaint_pipe.scheduler.config,**kwargs)
        except Exception: pass
        if int(seed)<0:
            import secrets; seed=secrets.randbelow(2147483646)+1
        g=torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(int(seed))

        neg=merge_negative_prompt(negative_prompt,False)
        context_prompt=(
            "precise seamless image edit, preserve all unmasked content, "
            "match the original camera perspective, scale, lighting direction, "
            "shadows, color temperature, depth of field, material texture and grain, "
            "natural boundary transition, " + self._prepare_prompt(prompt)
        )
        context_negative=(
            neg + ", hard rectangular edges, visible seam, pasted patch, collage, "
            "misaligned perspective, inconsistent lighting, inconsistent color, "
            "halo, ghosting, duplicated features, warped boundary, texture discontinuity"
        )

        with self._lock:
            generated=self.inpaint_pipe(
                prompt=context_prompt,
                negative_prompt=self._prepare_prompt(context_negative),
                image=work,
                mask_image=work_mask,
                height=wh,
                width=ww,
                num_inference_steps=steps,
                guidance_scale=guidance,
                generator=g,
            ).images[0]

        # Critical fix: map the generated crop back to the EXACT source crop size.
        generated_crop=generated.resize(original_crop_size,Image.Resampling.LANCZOS)
        composed=src.copy()
        composed.paste(generated_crop,(l,t),composite_crop_mask)

        os.makedirs(config.GENERATED_IMAGES_DIR,exist_ok=True)
        name=f"{uuid.uuid4().hex}.png"; out_path=os.path.join(config.GENERATED_IMAGES_DIR,name)
        composed.save(out_path)
        return {
            "url":"/static/generated/"+name,"width":composed.width,"height":composed.height,
            "seed":int(seed),"sampler":sampler,"generation_ms":0,"loras":[],
            "model":os.path.basename(self.inpaint_model_path or ""),"model_family":"SD 1.5 Inpainting",
            "inpaint":True,"crop_box":list(crop_box),"working_size":[ww,wh],"exact_unmasked_preservation":True,
        }

    def outpaint(self,prompt,image_data,direction="down",pixels=512,steps=30,guidance=5.2,seed=-1,sampler="DPM++ 2M Karras",style=""):
        """Extend an image and synthesize only the newly added canvas area using the dedicated inpaint checkpoint."""
        if not image_data or "," not in image_data: raise ValueError("Valid source image data is required.")
        self.load_inpaint()
        raw=base64.b64decode(image_data.split(",",1)[1],validate=True); src=Image.open(io.BytesIO(raw)).convert("RGB")
        px=max(128,min(int(pixels),768)); direction=str(direction or "down").lower()
        if direction not in ("down","up","left","right"): direction="down"
        if direction in ("down","up"):
            canvas=Image.new("RGB",(src.width,src.height+px),(0,0,0)); box=(0,0,src.width,src.height) if direction=="down" else (0,px,src.width,px+src.height)
        else:
            canvas=Image.new("RGB",(src.width+px,src.height),(0,0,0)); box=(0,0,src.width,src.height) if direction=="right" else (px,0,px+src.width,src.height)
        canvas.paste(src,box)
        mask=Image.new("L",canvas.size,0); md=mask.load()
        if direction=="down":
            for y in range(src.height,canvas.height):
                for x in range(canvas.width): md[x,y]=255
        elif direction=="up":
            for y in range(0,px):
                for x in range(canvas.width): md[x,y]=255
        elif direction=="right":
            for y in range(canvas.height):
                for x in range(src.width,canvas.width): md[x,y]=255
        else:
            for y in range(canvas.height):
                for x in range(0,px): md[x,y]=255
        # Add a small overlap so the new content can match the original edge.
        overlap=32
        if direction=="down":
            mdmask=Image.new("L",canvas.size,0); mdmask.paste(mask,(0,0)); mask=mdmask.filter(ImageFilter.GaussianBlur(2))
        target=768
        scale=min(1.0,target/max(canvas.width,canvas.height))
        if scale<1:
            nw=max(512,int(canvas.width*scale)//64*64); nh=max(512,int(canvas.height*scale)//64*64)
            canvas=canvas.resize((nw,nh),Image.Resampling.LANCZOS); mask=mask.resize((nw,nh),Image.Resampling.NEAREST)
        prompt=apply_style_prompt(prompt,style)
        steps=max(16,min(int(steps),50)); guidance=max(3.5,min(float(guidance),7.0))
        clsname,kwargs=SCHEDULERS.get(sampler,SCHEDULERS["DPM++ 2M Karras"])
        try:
            import diffusers, torch
            self.inpaint_pipe.scheduler=getattr(diffusers,clsname).from_config(self.inpaint_pipe.scheduler.config,**kwargs)
            if int(seed)<0:
                import secrets; seed=secrets.randbelow(2147483646)+1
            g=torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(int(seed))
            with self._lock:
                out=self.inpaint_pipe(prompt=self._prepare_prompt(prompt),negative_prompt=self._prepare_prompt(merge_negative_prompt("")),image=canvas,mask_image=mask,num_inference_steps=steps,guidance_scale=guidance,generator=g).images[0]
        except Exception as e:
            raise RuntimeError(f"Outpaint failed: {e}") from e
        # Preserve the original pixels exactly.
        if out.size!=canvas.size: out=out.resize(canvas.size,Image.Resampling.LANCZOS)
        inv=Image.eval(mask,lambda p:255-p)
        out.paste(canvas,(0,0),inv)
        os.makedirs(config.GENERATED_IMAGES_DIR,exist_ok=True); name=f"{uuid.uuid4().hex}.png"; out.save(os.path.join(config.GENERATED_IMAGES_DIR,name))
        return {"url":"/static/generated/"+name,"width":out.width,"height":out.height,"seed":int(seed),"sampler":sampler,"generation_ms":0,"loras":[],"model":os.path.basename(self.inpaint_model_path or ""),"model_family":"SD 1.5 Inpainting","outpaint":True}

    def faceid_status(self):
        sd15_adapter=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sd15.bin")
        sd15_lora=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sd15_lora.safetensors")
        sdxl_adapter=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sdxl.bin")
        sdxl_lora=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sdxl_lora.safetensors")
        enc=os.path.join(config.IP_ADAPTER_IMAGE_ENCODER_DIR,"model.safetensors")
        cfg=os.path.join(config.IP_ADAPTER_IMAGE_ENCODER_DIR,"config.json")
        insight=self._module_available("insightface")
        encoder=os.path.isfile(enc) and os.path.isfile(cfg)
        sd15=all((os.path.isfile(sd15_adapter),os.path.isfile(sd15_lora),encoder,insight))
        sdxl=all((os.path.isfile(sdxl_adapter),os.path.isfile(sdxl_lora),encoder,insight))
        return {
            "adapter":os.path.isfile(sd15_adapter),"lora":os.path.isfile(sd15_lora),
            "sd15_adapter":os.path.isfile(sd15_adapter),"sd15_lora":os.path.isfile(sd15_lora),
            "sdxl_adapter":os.path.isfile(sdxl_adapter),"sdxl_lora":os.path.isfile(sdxl_lora),
            "image_encoder":encoder,"insightface_installed":insight,
            "sd15_ready":sd15,"sdxl_ready":sdxl,"ready":sd15,
            "adapter_path":sd15_adapter,"lora_path":sd15_lora,
            "sdxl_adapter_path":sdxl_adapter,"sdxl_lora_path":sdxl_lora,
            "image_encoder_path":config.IP_ADAPTER_IMAGE_ENCODER_DIR
        }

    @staticmethod
    def _module_available(name):
        try:
            __import__(name); return True
        except Exception: return False

    def _unload_faceid(self):
        if self.faceid_pipe is not None:
            try: del self.faceid_pipe
            except Exception: pass
        self.faceid_pipe=None; self.faceid_model_path=None; self.faceid_family=""
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available(): torch.cuda.empty_cache(); torch.cuda.ipc_collect()
        except Exception: pass

    def _faceid_paths(self, family):
        st=self.faceid_status()
        if not st["image_encoder"]: raise RuntimeError("Missing CLIP image encoder: models\\ip_adapter\\faceid\\image_encoder\\config.json + model.safetensors")
        if not st["insightface_installed"]: raise RuntimeError("Missing Python package insightface. Install it in the newAIr venv.")
        if family == "SD 1.5":
            adapter=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sd15.bin")
            lora=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sd15_lora.safetensors")
        elif family in ("SDXL","Pony/SDXL"):
            adapter=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sdxl.bin")
            lora=os.path.join(config.IP_ADAPTER_DIR,"ip-adapter-faceid-plusv2_sdxl_lora.safetensors")
        else:
            raise RuntimeError(f"FaceID is not supported for model family: {family}")
        if not os.path.isfile(adapter) or not os.path.isfile(lora):
            missing=[]
            if not os.path.isfile(adapter): missing.append(os.path.basename(adapter))
            if not os.path.isfile(lora): missing.append(os.path.basename(lora))
            raise RuntimeError(f"FaceID adapter for {family} is missing: {', '.join(missing)}")
        return adapter,lora,config.IP_ADAPTER_IMAGE_ENCODER_DIR

    def _build_faceid_pipe(self, model_name=None):
        import torch
        from transformers import CLIPVisionModelWithProjection
        from diffusers import StableDiffusionPipeline, StableDiffusionXLPipeline, DDIMScheduler
        target=model_name or self.model_path
        if not target: raise RuntimeError("Choose an image generation model first.")
        target_path=self._safe_model_path(os.path.basename(target),config.IMAGE_MODELS_DIR) if not os.path.isabs(target) else os.path.realpath(target)
        family=self._profile_for(target_path)["family"]
        adapter_path,lora_path,encoder_path=self._faceid_paths(family)
        if self.faceid_pipe is not None and os.path.realpath(self.faceid_model_path or "") == os.path.realpath(target_path):
            return self.faceid_pipe
        if not os.path.isfile(target_path): raise FileNotFoundError(target_path)
        self._unload_faceid()
        self._unload_current()
        try:
            from core.llm_engine import engine as text_engine; text_engine.unload_model()
        except Exception: pass
        dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        image_encoder=CLIPVisionModelWithProjection.from_pretrained(encoder_path,torch_dtype=dtype,local_files_only=True)
        if family == "SD 1.5":
            pipe=StableDiffusionPipeline.from_single_file(target_path,torch_dtype=dtype,local_files_only=True,use_safetensors=target_path.lower().endswith(".safetensors"),image_encoder=image_encoder)
        else:
            pipe=StableDiffusionXLPipeline.from_single_file(target_path,torch_dtype=dtype,local_files_only=True,use_safetensors=target_path.lower().endswith(".safetensors"),image_encoder=image_encoder)
        pipe.scheduler=DDIMScheduler.from_config(pipe.scheduler.config)
        pipe.load_ip_adapter(config.IP_ADAPTER_DIR,subfolder=None,weight_name=os.path.basename(adapter_path),image_encoder_folder=None)
        try: pipe.set_ip_adapter_scale(0.9)
        except Exception: pass
        try:
            pipe.load_lora_weights(lora_path,adapter_name="faceid_plusv2")
            if hasattr(pipe,"set_adapters"): pipe.set_adapters(["faceid_plusv2"],[0.8])
        except Exception as e:
            # Keep the actual adapter load error visible rather than silently
            # producing an identity-free result.
            raise RuntimeError(f"Could not load the FaceID LoRA for {family}: {e}") from e
        if hasattr(pipe.vae,"enable_slicing"): pipe.vae.enable_slicing()
        if hasattr(pipe.vae,"enable_tiling"): pipe.vae.enable_tiling()
        if torch.cuda.is_available():
            if hasattr(pipe,"enable_sequential_cpu_offload"): pipe.enable_sequential_cpu_offload()
            else: pipe.enable_model_cpu_offload()
        else: pipe.to("cpu")
        self.faceid_pipe=pipe; self.faceid_model_path=target_path; self.faceid_family=family
        return pipe

    def face_to_scene(self,prompt,negative_prompt,image_data,identity_strength=0.9,steps=28,guidance=5.5,seed=-1,style="photorealistic",width=768,height=1024,model_name=None):
        if not image_data or "," not in image_data: raise ValueError("A face reference image is required.")
        pipe=self._build_faceid_pipe(model_name)
        try:
            import cv2, numpy as np, torch
            from insightface.app import FaceAnalysis
            from insightface.utils import face_align
        except Exception as e:
            raise RuntimeError("FaceID requires insightface, opencv-python and numpy. Run the FaceID setup command from FACEID_SETUP.md.") from e
        raw=base64.b64decode(image_data.split(",",1)[1],validate=True)
        pil=Image.open(io.BytesIO(raw)).convert("RGB")
        arr=np.asarray(pil)[:,:,::-1].copy()
        app=FaceAnalysis(name="buffalo_l",root=getattr(config,"INSIGHTFACE_DIR",None) or None,providers=['CUDAExecutionProvider','CPUExecutionProvider'])
        app.prepare(ctx_id=0 if torch.cuda.is_available() else -1,det_size=(640,640))
        faces=app.get(arr)
        if not faces: raise ValueError("No face was detected in the reference image.")
        face=max(faces,key=lambda f: float(getattr(f,"det_score",0.0)))
        faceid=torch.from_numpy(face.normed_embedding).unsqueeze(0)
        faceid=torch.stack([torch.zeros_like(faceid),faceid],dim=0).to(dtype=torch.float16 if torch.cuda.is_available() else torch.float32,device="cuda" if torch.cuda.is_available() else "cpu")
        aligned=face_align.norm_crop(arr,landmark=face.kps,image_size=224)[:,:,::-1].copy()
        clip_embeds=pipe.prepare_ip_adapter_image_embeds([Image.fromarray(aligned)],None,torch.device("cuda" if torch.cuda.is_available() else "cpu"),1,True)[0]
        layer=pipe.unet.encoder_hid_proj.image_projection_layers[0]
        layer.clip_embeds=clip_embeds.to(dtype=torch.float16 if torch.cuda.is_available() else torch.float32)
        layer.shortcut=False
        try: pipe.set_ip_adapter_scale(max(0.3,min(float(identity_strength),1.3)))
        except Exception: pass
        prompt=apply_style_prompt(prompt,style)
        negative_prompt=merge_negative_prompt(negative_prompt)
        width,height=self._normalize_dimensions_for_faceid(width,height)
        steps=max(12,min(int(steps),50)); guidance=max(3.5,min(float(guidance),8.0))
        if int(seed)<0:
            import secrets; seed=secrets.randbelow(2147483646)+1
        gen=torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(int(seed))
        with self._lock:
            result=pipe(prompt=self._prepare_prompt(prompt),negative_prompt=self._prepare_prompt(negative_prompt),ip_adapter_image_embeds=[faceid],width=width,height=height,num_inference_steps=steps,guidance_scale=guidance,generator=gen).images[0]
        os.makedirs(config.GENERATED_IMAGES_DIR,exist_ok=True); name=f"{uuid.uuid4().hex}.png"; result.save(os.path.join(config.GENERATED_IMAGES_DIR,name))
        return {"url":"/static/generated/"+name,"width":result.width,"height":result.height,"seed":int(seed),"sampler":"FaceID Plus V2","generation_ms":0,"loras":[],"model":os.path.basename(self.faceid_model_path or ""),"model_family":f"{self.faceid_family} + FaceID Plus V2","faceid":True}

    def _normalize_dimensions_for_faceid(self,width,height):
        width=max(512,min(int(width),1024)); height=max(512,min(int(height),1280))
        budget=786432
        if width*height>budget:
            scale=(budget/(width*height))**0.5; width=int(width*scale); height=int(height*scale)
        return max(512,(width//64)*64),max(512,(height//64)*64)

    def gpu_status(self):
        try:
            import torch
            if torch.cuda.is_available():
                free,total=torch.cuda.mem_get_info(); used=total-free
                return {"available":True,"name":torch.cuda.get_device_name(0),"total":total,"used":used,"free":free,"total_gb":round(total/1073741824,2),"used_gb":round(used/1073741824,2),"free_gb":round(free/1073741824,2)}
        except Exception as e: return {"available":False,"error":str(e)}
        return {"available":False,"error":"CUDA unavailable"}

image_engine=ImageEngine()
