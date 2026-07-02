"""FastAPI 后端入口。

本文件只声明课设项目需要的接口结构，具体业务逻辑后续在对应模块中实现。
"""

import json

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas import (
    CodeExportRequest,
    ModelRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
    TrainRequest,
    UserCreateRequest,
    UserUpdateRequest,
)

from .validator import validate_model_graph
from .trainer import (
    create_training_job,
    get_job_result,
    get_job_status,
    run_training_job,
)


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


@app.get("/health")
def health_check():
    """检查后端服务是否正常运行。

    参数：
        无。

    返回：
        后续应返回服务状态信息，例如 {"status": "ok"}。
    """
    pass


@app.get("/devices")
def list_devices():
    """返回当前本机可用的计算设备，例如 CPU 和 CUDA GPU。

    参数：
        无。

    返回：
        后续应返回设备列表和默认设备信息，供前端渲染设备选择器。
    """
    pass


@app.post("/validate")
def validate_model(request: ModelRequest):
    """校验模型结构，并推导每一层的张量维度变化。

    参数：
        request：模型校验请求体，包含前端画布生成的模型图结构。

    返回：
        后续应返回校验是否通过、错误节点、错误说明和每层维度信息。
    """
    return validate_model_graph(request.model.model_dump())


@app.post("/train")
def start_training(request: TrainRequest, background_tasks: BackgroundTasks):
    """根据用户选择的 CPU 或 GPU 启动本地训练任务。

    在创建训练任务前，先执行结构校验（对应系统约束 C5：未通过 Validate 的
    模型不允许进入训练）。只有结构合法的模型才会创建任务并在后台开始训练。

    参数：
        request：训练请求体，包含模型图结构和训练配置。
        background_tasks：FastAPI 后台任务，用于异步执行训练流程。

    返回：
        训练任务编号、初始状态和总轮数；结构校验失败时返回 400。
    """
    model_graph = request.model.model_dump()

    validation = validate_model_graph(model_graph)
    if not validation["valid"]:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "结构校验未通过，无法开始训练",
                "errors": validation["errors"],
            },
        )

    train_config = request.train_config.model_dump()
    job = create_training_job(
        model_graph=json.dumps(model_graph),
        train_config=train_config,
    )

    background_tasks.add_task(run_training_job, job["job_id"])

    return {
        "status": "ok",
        "job_id": job["job_id"],
        "job_status": job["status"],
        "current_epoch": job["current_epoch"],
        "total_epochs": job["total_epochs"],
    }


@app.get("/train/{job_id}/status")
def get_training_status(job_id: str):
    """返回指定训练任务的当前状态、日志和进度。

    参数：
        job_id：训练任务编号，用于定位某一次本地训练任务。

    返回：
        任务状态、当前 epoch、进度百分比和逐轮指标；任务不存在时返回 404。
    """
    try:
        return get_job_status(job_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/train/{job_id}/result")
def get_training_result(job_id: str):
    """返回训练完成后的最终指标和相关产物信息。

    参数：
        job_id：训练任务编号，用于查询对应训练任务的最终结果。

    返回：
        loss、accuracy、模型文件路径和训练摘要；任务不存在时返回 404。
    """
    try:
        return get_job_result(job_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/export/pytorch")
def export_pytorch_code(request: CodeExportRequest):
    """根据可视化模型结构生成 PyTorch 源代码。

    参数：
        request：代码导出请求体，包含模型图结构和导出类名。

    返回：
        后续应返回生成的 PyTorch 源代码字符串。
    """
    pass


# ============================================================
# M1 用户与项目管理模块
# 编写者：甘淞文
# ============================================================

@app.post("/users")
def create_user(request: UserCreateRequest):
    """创建新用户。

    参数：
        request：创建用户请求体，包含 username 和 email。

    返回：
        创建成功的用户信息，包含 id、username、email、created_at。
    """
    from .auth import create_user as _create_user

    try:
        user = _create_user(
            username=request.username,
            email=request.email,
        )
        return {"status": "ok", "data": user}
    except ValueError as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/users")
def list_users():
    """获取所有用户列表。

    参数：
        无。

    返回：
        用户字典列表。
    """
    from .auth import list_users as _list_users

    users = _list_users()
    return {"status": "ok", "data": users, "count": len(users)}


@app.get("/users/{user_id}")
def get_user(user_id: str):
    """获取指定用户信息。

    参数：
        user_id：用户唯一标识。

    返回：
        用户详情字典；不存在时返回 404。
    """
    from .auth import get_user as _get_user
    from fastapi.responses import JSONResponse

    try:
        user = _get_user(user_id)
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
    """更新用户信息。

    参数：
        user_id：用户唯一标识。
        request：更新请求体，包含可选的 username 和 email。

    返回：
        更新后的用户信息。
    """
    from .auth import update_user as _update_user
    from fastapi.responses import JSONResponse

    try:
        user = _update_user(
            user_id=user_id,
            username=request.username,
            email=request.email,
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
    """删除用户及其所有项目。

    参数：
        user_id：用户唯一标识。

    返回：
        删除结果。
    """
    from .auth import delete_user as _delete_user
    from fastapi.responses import JSONResponse

    try:
        _delete_user(user_id)
        return {"status": "ok", "message": f"用户 '{user_id}' 已删除"}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/users/{user_id}/projects")
def get_user_projects(user_id: str):
    """获取指定用户的所有项目。

    参数：
        user_id：用户唯一标识。

    返回：
        项目列表。
    """
    from .projects import get_user_projects as _get_user_projects
    from fastapi.responses import JSONResponse

    try:
        projects = _get_user_projects(user_id)
        return {"status": "ok", "data": projects, "count": len(projects)}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.post("/projects")
def create_project(request: ProjectCreateRequest):
    """创建新项目（保存模型）。

    参数：
        request：创建项目请求体，包含 user_id、name、model_graph 和可选的 description。

    返回：
        创建成功的项目信息。
    """
    from .projects import create_project as _create_project
    from fastapi.responses import JSONResponse

    try:
        project = _create_project(
            user_id=request.user_id,
            name=request.name,
            model_graph=request.model_graph.model_dump(),
            description=request.description,
        )
        return {"status": "ok", "data": project}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/projects")
def list_projects(user_id: str | None = None):
    """获取项目列表，可按用户过滤。

    参数：
        user_id：可选，按所属用户过滤。

    返回：
        项目列表。
    """
    from .projects import list_projects as _list_projects

    projects = _list_projects(user_id=user_id)
    return {"status": "ok", "data": projects, "count": len(projects)}


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """获取指定项目详情。

    参数：
        project_id：项目唯一标识。

    返回：
        项目详情字典；不存在时返回 404。
    """
    from .projects import get_project as _get_project
    from fastapi.responses import JSONResponse

    try:
        project = _get_project(project_id)
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
def update_project(project_id: str, request: ProjectUpdateRequest):
    """更新项目信息。

    参数：
        project_id：项目唯一标识。
        request：更新请求体，包含可选的 name、model_graph 和 description。

    返回：
        更新后的项目信息。
    """
    from .projects import update_project as _update_project
    from fastapi.responses import JSONResponse

    try:
        project = _update_project(
            project_id=project_id,
            name=request.name,
            model_graph=request.model_graph.model_dump() if request.model_graph else None,
            description=request.description,
        )
        return {"status": "ok", "data": project}
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


@app.delete("/projects/{project_id}")
def delete_project(project_id: str):
    """删除项目。

    参数：
        project_id：项目唯一标识。

    返回：
        删除结果。
    """
    from .projects import delete_project as _delete_project
    from fastapi.responses import JSONResponse

    try:
        _delete_project(project_id)
        return {"status": "ok", "message": f"项目 '{project_id}' 已删除"}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(exc)},
        )
