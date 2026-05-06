from __future__ import annotations

import open_clip
import torch
from PIL import Image

from app.config import settings

_model: open_clip.CLIP | None = None
_preprocess = None
_device: str = "cpu"


def _load_model() -> None:
    global _model, _preprocess, _device
    if _model is not None:
        return
    _device = settings.clip_device if torch.cuda.is_available() else "cpu"
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        settings.clip_model_name,
        pretrained=settings.clip_pretrained,
        device=_device,
    )
    _model.eval()


def encode_image(image: Image.Image) -> list[float]:
    _load_model()
    assert _model is not None and _preprocess is not None
    tensor = _preprocess(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        features = _model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)
    result: list[float] = features.squeeze(0).cpu().tolist()
    return result
