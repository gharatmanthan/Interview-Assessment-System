from fastapi import APIRouter
from api.schemas import LoginRequest, RegisterRequest, AuthResponse
from app.core.auth import register_recruiter, verify_recruiter

router = APIRouter()


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest):
    success, message = verify_recruiter(req.username, req.password)
    return AuthResponse(success=success, message=message, username=req.username if success else None)


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    success, message = register_recruiter(req.username, req.password, req.full_name)
    return AuthResponse(success=success, message=message, username=req.username if success else None)
