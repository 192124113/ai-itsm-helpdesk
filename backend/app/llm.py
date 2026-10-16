"""LLM access: a small open-source Hugging Face model running locally.

Default model: Qwen/Qwen2.5-1.5B-Instruct - open weights (Apache-2.0), good instruction
following for its size, and small enough to run on a laptop CPU with no API credits.
Any chat model can be swapped in with HF_MODEL.

If loading or generation fails, `generate` returns None and callers use deterministic
fallbacks, so the demo never breaks.
"""
import logging
import threading

from .config import settings

log = logging.getLogger(__name__)
_tok = None
_model = None
_lock = threading.Lock()


def _load():
    global _tok, _model
    if _model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        log.info("Loading local LLM %s (first time downloads it)...", settings.HF_MODEL)
        _tok = AutoTokenizer.from_pretrained(settings.HF_MODEL)
        _model = AutoModelForCausalLM.from_pretrained(settings.HF_MODEL)
        _model.eval()
        log.info("Local LLM loaded.")


def generate(system: str, user: str, max_tokens: int = 400) -> str | None:
    try:
        import torch

        with _lock:
            _load()
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            text = _tok.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = _tok(text, return_tensors="pt")
            with torch.no_grad():
                out = _model.generate(
                    **inputs,
                    max_new_tokens=min(max_tokens, 300),
                    do_sample=False,
                )
            new_tokens = out[0][inputs["input_ids"].shape[1]:]
            return _tok.decode(new_tokens, skip_special_tokens=True).strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Local LLM failed (%s); using fallback", exc)
        return None