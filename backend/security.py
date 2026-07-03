"""安全模块 —— 密码哈希、JWT 令牌、用户会话管理。

提供：
- bcrypt 密码哈希与验证
- JWT 访问令牌的生成与验证
- FastAPI Depends 依赖：从 Authorization Header 提取当前登录用户
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# ============================================================
# 密码哈希配置
# ============================================================

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希，返回哈希后的字符串。"""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与 bcrypt 哈希值是否匹配。"""
    return _pwd_context.verify(plain_password, hashed_password)


# ============================================================
# JWT 令牌配置
# ============================================================

# 优先从环境变量读取密钥，开发环境使用固定默认值
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def create_access_token(user_id: str, expires_minutes: Optional[int] = None) -> str:
    """为用户生成 JWT 访问令牌。

    参数：
        user_id：用户唯一标识。
        expires_minutes：令牌有效分钟数，默认使用 ACCESS_TOKEN_EXPIRE_MINUTES。

    返回：
        JWT 字符串。
    """
    expire_minutes = expires_minutes if expires_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Dict[str, Any]:
    """验证 JWT 令牌，返回解码后的 payload。

    参数：
        token：JWT 字符串。

    返回：
        解码后的 payload 字典。

    异常：
        HTTPException：令牌无效或已过期。
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="令牌无效：缺少用户标识",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
        )


# ============================================================
# FastAPI 认证依赖
# ============================================================

# HTTP Bearer 认证方案
_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    """FastAPI 依赖：从 Authorization: Bearer <token> 头中提取当前登录用户。

    使用方式：
        @app.get("/protected")
        def protected_route(current_user = Depends(get_current_user)):
            ...

    返回：
        当前登录用户的字典。

    异常：
        HTTPException 401：未提供令牌或令牌无效/用户不存在。
    """
    from .auth import get_user as _get_user

    payload = verify_access_token(credentials.credentials)
    user_id = payload["sub"]

    user = _get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
        )

    return user
