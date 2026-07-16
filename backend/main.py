"""FastAPI 后端入口。

本文件声明课设项目需要的接口结构，具体业务逻辑在对应模块中实现。

M1：用户 CRUD + 项目 CRUD + /auth/* 认证路由 + JWT 令牌 + 权限控制
M3：模型校验、形状推导
"""

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Body, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from local_agent.runtime.validator import validate_model_graph

from . import auth as auth_mgr
from . import projects as project_mgr
from .cloud_training import (
    router as cloud_training_router,
    start_agent_heartbeat_cleanup,
    stop_agent_heartbeat_cleanup,
)
from .assistant import router as assistant_router
from .teaching_api import router as teaching_router
from .schemas import (
    ProjectCreateRequest,
    ProjectTemplateCreateRequest,
    ProjectUpdateRequest,
    TokenResponse,
    UserCreateRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserUpdateRequest,
)
from .security import create_access_token, get_current_user


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """管理云端后台任务的启动与干净退出。"""
    await start_agent_heartbeat_cleanup()
    try:
        yield
    finally:
        await stop_agent_heartbeat_cleanup()


app = FastAPI(title="Visual Deep Learning Model Builder", lifespan=lifespan)

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


@app.post("/validate")
def validate_structure(payload: Dict[str, Any] = Body(...)):
    """在云端做模型结构校验与维度推导（纯 Python，无需本地 Agent）。

    结构检查、每层输出尺寸推导都在此完成，因此用户**不必先下载/运行本地 Agent**
    即可检查模型是否正确、实时预览各层形状；训练才需要本地 Agent。

    请求体：{"model": {"layers": [...], "connections": [...]}}
    返回：{valid, errors, warnings, shapes, message}
    """
    model = payload.get("model", payload)
    return validate_model_graph(model)


app.include_router(cloud_training_router)
app.include_router(assistant_router)
app.include_router(teaching_router)


# M1 认证路由（编写者：甘淞文）
# ============================================================

@app.post("/auth/register", response_model=TokenResponse)
def register(request: UserRegisterRequest):
    """注册新用户，返回 JWT 令牌和用户信息。

    参数：
        request：注册请求体，包含 username、email、password、confirm_password
        （确认密码，需与 password 一致）。
    """
    try:
        user = auth_mgr.register_user(
            username=request.username,
            email=request.email,
            password=request.password,
            confirm_password=request.confirm_password,
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
def create_user(
    request: UserCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建新用户（需要登录）。

    说明：
        面向用户的自助注册请走 /auth/register。此接口要求已登录身份，
        避免匿名调用批量创建用户。

    参数：
        request：创建用户请求体，包含 username、email、password。
    """
    try:
        user = auth_mgr.register_user(
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
def list_users(current_user: dict = Depends(get_current_user)):
    """获取用户列表（需要登录）。

    本系统无管理员角色，为避免任意用户枚举全站账号信息，
    此接口只返回当前登录用户本人的记录。
    """
    users = [current_user]
    return {"status": "ok", "data": users, "count": len(users)}


@app.get("/users/{user_id}")
def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取指定用户信息（需要登录且只能查看本人账号）。"""
    if current_user["id"] != user_id:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "无权操作：只能查看本人账号"},
        )

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
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新用户信息（支持修改密码，需要登录且只能修改本人账号）。"""
    if current_user["id"] != user_id:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "无权操作：只能修改本人账号"},
        )
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
def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除用户及其所有项目（需要登录且只能删除本人账号）。"""
    if current_user["id"] != user_id:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "无权操作：只能删除本人账号"},
        )
    try:
        auth_mgr.delete_user(user_id)
        return {"status": "ok", "message": f"用户 '{user_id}' 已删除"}
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


@app.get("/projects/templates")
def list_project_templates():
    """获取可用于创建项目的内置模型模板列表。"""
    from .templates import get_available_templates

    templates = get_available_templates()
    return {"status": "ok", "data": templates, "count": len(templates)}


@app.get("/projects/templates/{template_name}")
def get_project_template(template_name: str):
    """获取指定模板的完整模型图。"""
    from .templates import apply_template
    from fastapi.responses import JSONResponse

    result = apply_template(template_name)
    if result.get("status") != "ok":
        return JSONResponse(
            status_code=404,
            content=result,
        )

    return result


@app.post("/projects/from-template")
def create_project_from_template(
    request: ProjectTemplateCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """基于内置模板创建项目（需要登录），并复用 /projects 的项目存储逻辑。"""
    from .projects import create_project as _create_project
    from .templates import apply_template, get_available_templates
    from fastapi.responses import JSONResponse

    template_result = apply_template(request.template_name)
    if template_result.get("status") != "ok":
        return JSONResponse(
            status_code=404,
            content=template_result,
        )

    template_meta = next(
        (
            template
            for template in get_available_templates()
            if template["key"] == template_result["template"]
        ),
        None,
    )
    project_name = request.name or (
        f"{template_meta['name']} Project" if template_meta else f"{request.template_name} Project"
    )
    description = request.description
    if description is None and template_meta:
        description = template_meta.get("description")

    try:
        project = _create_project(
            user_id=current_user["id"],
            name=project_name,
            model_graph=template_result["model"],
            description=description,
            current_user_id=current_user["id"],
        )
        return {"status": "ok", "data": project, "template": template_result["template"]}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/projects")
def list_projects(current_user: dict = Depends(get_current_user)):
    """获取当前登录用户的项目列表（需要登录）。

    强制按 token 中的用户过滤，用户只能看到自己的项目，
    不接受调用方自行指定 user_id，避免越权读取他人项目。
    """
    try:
        projects = project_mgr.list_projects(user_id=current_user["id"])
        return {"status": "ok", "data": projects, "count": len(projects)}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/projects/{project_id}")
def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取指定项目详情（需要登录且只能查看本人项目）。"""
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

    if project.get("user_id") != current_user["id"]:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": "无权访问：您不是项目所有者"},
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

