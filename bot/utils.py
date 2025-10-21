from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import qrcode
import yaml


@dataclass
class BotConfig:
    links: Dict[str, Any]
    texts: Dict[str, Any]
    postman_mapping: Dict[str, str]
    defaults: Dict[str, Any]


def load_yaml_config(path: Path) -> BotConfig:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return BotConfig(
        links=data.get("links", {}),
        texts=data.get("texts", {}),
        postman_mapping=data.get("postman_mapping", {}),
        defaults=data.get("defaults", {}),
    )


def ensure_png_bytes(qr_base64: str | None, uri: str) -> bytes:
    if qr_base64:
        return base64.b64decode(qr_base64)
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    try:
        # для PIL-рендерера
        image.save(buffer, format="PNG")
    except TypeError:
        # для PyPNG-рендерера (не принимает параметр "format")
        image.save(buffer)
    buffer.seek(0)
    return buffer.read()
