from pydantic import BaseModel


class UsageOut(BaseModel):
    plan: str
    accounts_used: int
    accounts_limit: int
    jobs_today_used: int
    jobs_today_limit: int
