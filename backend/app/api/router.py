from fastapi import APIRouter

from app.api import auth, metadata, public, wishlists

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(wishlists.router)
api_router.include_router(public.router)
api_router.include_router(metadata.router)

