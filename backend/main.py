"""FastAPI 后端入口。

本文件声明课设项目需要的接口结构，具体业务逻辑在对应模块中实现。

M1（甘淞文）：用户 CRUD + 项目 CRUD + /auth/* 认证路由 + JWT 令牌 + 权限控制
M3：模型校验、形状推导
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth as auth_mgr
from . import projects as project_mgr
from .schemas import (
    CodeExportRequest,
    ModelRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TrainRequest,
    TokenResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserUpdateRequest,
)
from .security import create_access_token, get_current_user
from .validator import validate_model_graph


app = FastAPI(title="Visual Deep Learning Model Builder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 基础设施路由
# ============================================================

@app.get("/health")
def health_check():
    """返回后端服务健康状态。"""
    return {"status": "ok", "service": "Visual Deep Learning Model Builder"}


@app.get("/devices")
def list_devices():
    """返回当前本机可用的计算设备（尚未实现）。"""
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "设备检测功能尚未实现"},
    )


@app.post("/validate")
def validate_model(request: ModelRequest):
    """校验模型结构，并推导每一层的张量维度变化。"""
    try:
        result = validate_model_graph(request.model.model_dump())
        return result
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/train")
def start_training(request: TrainRequest):
    """启动本地训练任务（尚未实现）。"""
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "训练功能尚未实现"},
    )


@app.get("/train/{job_id}/status")
def get_training_status(job_id: str):
    """返回训练任务状态（尚未实现）。"""
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "训练功能尚未实现"},
    )


@app.get("/train/{job_id}/result")
def get_training_result(job_id: str):
    """返回训练结果（尚未实现）。"""
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "训练功能尚未实现"},
    )


@app.post("/export/pytorch")
def export_pytorch_code(request: CodeExportRequest):
    """导出 PyTorch 代码（尚未实现）。"""
    return JSONResponse(
        status_code=501,
        content={"status": "error", "message": "代码导出功能尚未实现"},
    )


# ============================================================
# M1 认证路由（编写者：甘淞文）
# ============================================================

@app.post("/auth/register", response_model=TokenResponse)
def register(request: UserRegisterRequest):
    """注册新用户，返回 JWT 令牌和用户信息。

    参数：
        request：注册请求体，包含 username、email、password。
    """
    try:
        user = auth_mgr.register_user(
            username=request.username,
            email=request.email,
            password=request.password,
        )
        token = create_access_token(user["id"])
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user,
        }
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/auth/login", response_model=TokenResponse)
def login(request: UserLoginRequest):
    """用户登录，验证凭据后返回 JWT 令牌。

    参数：
        request：登录请求体，包含 email、password。

    流程：
        1. 先检查邮箱是否已注册，未注册则提示用户先注册。
        2. 邮箱已注册则校验密码，匹配成功返回令牌（含用户名等信息）。
    """
    # 先检查邮箱是否已注册
    email_user = auth_mgr.get_user_by_email(request.email)
    if email_user is None:
        return JSONResponse(
            status_code=404,
            content={
                "status": "error",
                "message": f"邮箱 '{request.email}' 未注册，请先注册账号",
                "code": "NOT_REGISTERED",
            },
        )

    # 邮箱存在，校验密码
    user = auth_mgr.authenticate_user(
        email=request.email,
        password=request.password,
    )
    if user is None:
        return JSONResponse(
            status_code=401,
            content={"status": "error", "message": "邮箱或密码错误"},
        )

    token = create_access_token(user["id"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
    }


@app.get("/auth/me")
def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户的详细信息（需 Bearer Token）。

    请求头：
        Authorization: Bearer <token>
    """
    return {"status": "ok", "data": current_user}


# ============================================================
# M1 用户管理路由（编写者：甘淞文）
# ============================================================

@app.post("/users")
def create_user(request: UserCreateRequest):
    """创建新用户。

    参数：
        request：创建用户请求体，包含 username、email、password。
    """
    try:
        user = auth_mgr.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
        )
        return {"status": "ok", "data": user}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/users")
def list_users():
    """获取所有用户列表。"""
    users = auth_mgr.list_users()
    return {"status": "ok", "data": users, "count": len(users)}


@app.get("/users/{user_id}")
def get_user(user_id: str):
    """获取指定用户信息。"""
    try:
        user = auth_mgr.get_user(user_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )

    if user is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"用户 '{user_id}' 不存在"},
        )

    return {"status": "ok", "data": user}


@app.put("/users/{user_id}")
def update_user(user_id: str, request: UserUpdateRequest):
    """更新用户信息（支持修改密码）。"""
    try:
        user = auth_mgr.update_user(
            user_id=user_id,
            username=request.username,
            email=request.email,
            password=request.password,
        )
        return {"status": "ok", "data": user}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )


@app.delete("/users/{user_id}")
def delete_user(user_id: str):
    """删除用户及其所有项目。"""
    try:
        auth_mgr.delete_user(user_id)
        return {"status": "ok", "message": f"用户 '{user_id}' 已删除"}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/users/{user_id}/projects")
def get_user_projects(user_id: str):
    """获取指定用户的所有项目。"""
    try:
        projects = project_mgr.get_user_projects(user_id)
        return {"status": "ok", "data": projects, "count": len(projects)}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


# ============================================================
# M1 项目管理路由（编写者：甘淞文）
# ============================================================

@app.post("/projects")
def create_project(
    request: ProjectCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建新项目（需要登录）。

    请求头：
        Authorization: Bearer <token>
    """
    try:
        project = project_mgr.create_project(
            user_id=request.user_id,
            name=request.name,
            model_graph=request.model_graph.model_dump(),
            description=request.description,
            current_user_id=current_user["id"],
        )
        return {"status": "ok", "data": project}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )
    except PermissionError as exc:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/projects")
def list_projects(user_id: str | None = None):
    """获取项目列表，可按用户过滤。"""
    try:
        projects = project_mgr.list_projects(user_id=user_id)
        return {"status": "ok", "data": projects, "count": len(projects)}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """获取指定项目详情。"""
    try:
        project = project_mgr.get_project(project_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )

    if project is None:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"项目 '{project_id}' 不存在"},
        )

    return {"status": "ok", "data": project}


@app.put("/projects/{project_id}")
def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新项目信息（需要登录，且是项目所有者）。"""
    try:
        project = project_mgr.update_project(
            project_id=project_id,
            name=request.name,
            model_graph=request.model_graph.model_dump() if request.model_graph else None,
            description=request.description,
            current_user_id=current_user["id"],
        )
        return {"status": "ok", "data": project}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )
    except PermissionError as exc:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": str(exc)},
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )


@app.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除项目（需要登录，且是项目所有者）。"""
    try:
        project_mgr.delete_project(
            project_id=project_id,
            current_user_id=current_user["id"],
        )
        return {"status": "ok", "message": f"项目 '{project_id}' 已删除"}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )
    except PermissionError as exc:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": str(exc)},
        )
