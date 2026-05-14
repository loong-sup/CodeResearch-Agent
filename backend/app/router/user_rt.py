from fastapi import APIRouter, HTTPException, status
from exceptions.auth import  AuthError
from service.auth import authenticate, register_user
from pydantic import BaseModel
import logging

router = APIRouter()
# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义登录请求体的 Pydantic 模型
class LoginRequest(BaseModel):
    username: str
    password: str

# 用户认证接口
@router.post("/login")
async def login(request: LoginRequest):
    try:
        # 调用 authenticate 函数进行认证
        token = authenticate(request.username, request.password)
        return {"access_token": token, "token_type": "bearer"}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# 定义请求体的 Pydantic 模型
class RegisterRequest(BaseModel):
    username: str
    password: str

# 用户注册接口
@router.post("/register")
async def register(request: RegisterRequest):
    try:
        # 调用 register_user 函数进行注册
        register_user(request.username, request.password)
        return {"message": "User registered successfully"}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )