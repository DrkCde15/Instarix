from pydantic import BaseModel


class UploadOut(BaseModel):
    storage_key: str
    filename: str
    content_type: str
    size_bytes: int
