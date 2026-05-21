from unittest.mock import MagicMock, patch

import pytest
import torch

import app.clip_text as clip_text_module


@pytest.fixture(autouse=True)
def reset_clip_singleton() -> None:
    clip_text_module._model = None
    clip_text_module._tokenizer = None


def test_encode_text_returns_768_floats() -> None:
    fake_features = torch.ones(1, 768)

    mock_model = MagicMock()
    mock_model.encode_text.return_value = fake_features

    mock_tokenizer = MagicMock(return_value=torch.zeros(1, 77))

    with (
        patch(
            "app.clip_text.open_clip.create_model_and_transforms",
            return_value=(mock_model, None, None),
        ),
        patch("app.clip_text.open_clip.get_tokenizer", return_value=mock_tokenizer),
        patch("app.clip_text.torch.cuda.is_available", return_value=False),
    ):
        from app.clip_text import encode_text

        result = encode_text("beach")

    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)
