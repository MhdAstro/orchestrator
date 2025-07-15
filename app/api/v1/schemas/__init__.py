from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class ProductCreateByLinkRequest(BaseModel):
    """
    مدل ورودی برای ساخت محصول از طریق لینک.
    این مدل دقیقاً ساختار JSON ورودی شما را نمایندگی می‌کند.
    """
    description: str
    photo: HttpUrl  # لینک تصویر اصلی
    photos: List[HttpUrl]  # لیست لینک‌های سایر تصاویر
    video: Optional[HttpUrl] = None  # لینک ویدئو اختیاری است

    class Config:
        # نام مستعار برای فیلدها اگر در جیسون متفاوت باشد
        # در اینجا نیازی نیست چون نام‌ها یکی هستند
        schema_extra = {
            "example": {
                "description": "👚نام : ساحلی دنیا. 🧵جنس : تمام نخ",
                "photo": "https://i.postimg.cc/RSCmMMP2/photo.jpg",
                "photos": [
                    "https://i.postimg.cc/w6QH8tkh/photo.jpg",
                    "https://i.postimg.cc/3YkK4xKT/photo.jpg"
                ],
                "video": "https://example.com/video.mp4"
            }
        }