from fastapi import APIRouter

from app.api.v1 import health
from app.modules.attendance.router import router as attendance_router
from app.modules.geolocation.router import router as geolocation_router
from app.modules.identity.router import router as identity_router
from app.modules.institutions.router import router as institutions_router

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(identity_router)
api_router.include_router(institutions_router)
api_router.include_router(geolocation_router)
api_router.include_router(attendance_router)
