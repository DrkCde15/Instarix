from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("tenant_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("tenant_name não pode ser vazio")
        return value


class TokenIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=16)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: UUID
    tenant_id: UUID
    tenant_slug: str
    email: EmailStr
    role: str
