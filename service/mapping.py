from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


class MappingError(Exception):
    """Raised when panel payload cannot be mapped to service schema."""


def _get_data(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return raw.get("data") or raw
    raise MappingError("Unexpected panel payload type")


def _as_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"1", "true", "yes", "y", "enabled", "active"}:
            return True
        if s in {"0", "false", "no", "n", "disabled", "inactive"}:
            return False
    return None


def _extract_client(d: Mapping[str, Any]) -> Dict[str, Any]:
    # пытаемся заполнить максимально возможные поля
    email = d.get("email") or d.get("name") or d.get("username")
    uuid = d.get("uuid") or d.get("id") or d.get("panel_user_id")
    enabled = _as_bool(d.get("enable") or d.get("enabled") or d.get("active"))
    limits = d.get("limits") or {}
    return {
        "panel_user_id": uuid,
        "email": email,
        "enabled": enabled if enabled is not None else True,
        "limits": limits,
    }


def _extract_delivery(d: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    uri = d.get("uri") or d.get("url") or d.get("connection_uri")
    qr = d.get("qr") or d.get("qr_code") or d.get("qrCode")
    if not uri and not qr:
        # раньше мы падали, теперь просто возвращаем None
        return None
    out: Dict[str, Any] = {}
    if uri:
        out["uri"] = uri
    if qr:
        out["qr"] = qr
    return out


def normalize_key_payload(raw: Any) -> Dict[str, Any]:
    """
    Приводит ответ панели к виду:
    {
        "client": {...},
        "delivery": {...} | None,
        "raw": <исходный payload для отладки>
    }
    """
    data = _get_data(raw)
    client = _extract_client(data)
    delivery = _extract_delivery(data)  # может вернуться None
    if not client.get("email"):
        raise MappingError("Client email is missing in panel response")
    return {"client": client, "delivery": delivery, "raw": raw}


def normalize_revoke_payload(raw: Any) -> Dict[str, Any]:
    data = _get_data(raw)
    ok = _as_bool(data.get("ok") or data.get("success"))
    return {"ok": bool(ok) if ok is not None else True, "raw": raw}


def normalize_status_payload(raw: Any) -> Dict[str, Any]:
    data = _get_data(raw)
    active = _as_bool(data.get("active") or data.get("enabled"))
    return {"active": bool(active) if active is not None else False, "raw": raw}
