from fastapi import APIRouter
from api.schemas import SettingsUpdate, SettingsResponse
from app.core.settings_store import load_settings, save_settings

router = APIRouter()


@router.get("", response_model=SettingsResponse)
def get_settings():
    return load_settings()


@router.put("", response_model=SettingsResponse)
def update_settings(req: SettingsUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = save_settings(updates)
    return result
