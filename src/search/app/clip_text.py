from __future__ import annotations

from typing import Any

import open_clip
import torch

from app.config import settings

_model: Any = None
_tokenizer: Any = None
_device: str = "cpu"


def _load_model() -> None:
    global _model, _tokenizer, _device
    if _model is not None:
        return
    _device = settings.clip_device if torch.cuda.is_available() else "cpu"
    _model, _, _ = open_clip.create_model_and_transforms(
        settings.clip_model_name, pretrained=settings.clip_pretrained, device=_device
    )
    _tokenizer = open_clip.get_tokenizer(settings.clip_model_name)
    _model.eval()


def encode_text(query: str) -> list[float]:
    _load_model()
    tokens = _tokenizer([query]).to(_device)
    with torch.no_grad():
        features = _model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)
    result: list[float] = features.squeeze(0).cpu().tolist()
    return result
