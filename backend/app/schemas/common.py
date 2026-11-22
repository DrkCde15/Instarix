from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody


class MessageOut(BaseModel):
    message: str
