from fastapi import APIRouter

from app.api.v1 import accounts, api_keys, auth, jobs, me, media

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(accounts.router)
api_router.include_router(jobs.account_router)
api_router.include_router(jobs.router)
api_router.include_router(media.router)
api_router.include_router(api_keys.router)
