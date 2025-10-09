from __future__ import annotations

from typing import Any, Dict


class MappingError(Exception):
    """Raised when required fields are missing in panel responses."""


def _extract_delivery(data: Dict[str, Any]) -> Dict[str, Any]:
    uri = data.get("uri") or data.get("url") or data.get("connection_uri")
    if not uri:
        raise MappingError("Missing delivery URI in panel response")
    qr = (
        data.get("qr_png_base64")
        or data.get("qr_base64")
        or data.get("qr")
    )
    return {"uri": uri, "qr_png_base64": qr}


def _extract_client(data: Dict[str, Any]) -> Dict[str, Any]:
    panel_user_id = (
        data.get("panel_user_id")
        or data.get("user_id")
        or data.get("id")
        or data.get("client_id")
    )
    active = data.get("active")
    if active is None:
        active = data.get("status") in ("active", "enabled", True)
    return {
        "panel_user_id": str(panel_user_id) if panel_user_id is not None else None,
        "active": bool(active),
    }


def normalize_key_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    delivery = _extract_delivery(data)
    client = _extract_client(data)
    return {
        "delivery": delivery,
        "client": client,
    }


def normalize_status_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    active = data.get("active")
    if active is None:
        active = data.get("status") in ("active", True)
    return {"active": bool(active)}


def normalize_revoke_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {"revoked": True, "details": raw}
