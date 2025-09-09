from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class RawMessage(BaseModel):
    message: str

class RawDataJson(BaseModel):
    raw_message: RawMessage
    photos: List[HttpUrl]
    stock: int
    video: Optional[HttpUrl] = None

class TelegramWebhookPayload(BaseModel):
    raw_data_json: RawDataJson
    access_token: str