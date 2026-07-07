"""云端接口请求与响应数据结构。

该文件只保留服务器端需要的数据结构：用户认证、项目管理、模板创建
和训练任务中转。模型校验、训练配置校验、代码导出等本机训练运行时
结构已经迁移到 local_agent/runtime/schemas.py。
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CloudModelGraph(BaseModel):
    """云端保存和转发的模型图结构。

    云端不负责推导张量维度，也不负责构建 PyTorch 模型，因此这里只做
    轻量结构承载。更严格的模型校验由用户本机 Agent 完成。

    字段：
        layers：前端画布中的层节点列表，云端原样保存。
        connections：层节点之间的连接关系列表，云端原样保存。
    """

    layers: List[Dict[str, Any]]
    connections: List[Dict[str, Any]] = []


class CloudTrainRequest(BaseModel):
    """云端训练中转接口的请求体。

    云端接收该请求后只创建任务并转发给用户本机 Agent，不直接执行训练。

    字段：
        model：前端提交的模型图结构。
        train_config：训练配置字典，例如数据集、epoch、batch_size、
            学习率、设备、数据目录和产物目录等。具体字段由本机 Agent
            的 runtime schema 负责校验。
    """

    model: CloudModelGraph
    train_config: Dict[str, Any]


class UserCreateRequest(BaseModel):
    """创建用户接口的请求体。

    字段：
        username：用户名。
        email：用户邮箱。
        password：登录密码。
    """

    username: str
    email: str
    password: str


class UserUpdateRequest(BaseModel):
    """更新用户接口的请求体。

    字段：
        username：新的用户名，可选。
        email：新的邮箱，可选。
        password：新的密码，可选。
    """

    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


class UserRegisterRequest(BaseModel):
    """用户注册接口的请求体。

    字段：
        username：用户名。
        email：用户邮箱。
        password：登录密码。
        confirm_password：确认密码，必须与 password 一致。
    """

    username: str
    email: str
    password: str
    confirm_password: str

    def check_password(self) -> List[str]:
        """检查密码强度。

        返回：
            错误消息列表。列表为空表示密码满足基础要求。
        """
        errors = []
        if not isinstance(self.password, str):
            return ["password 必须是字符串"]
        if len(self.password) < 8:
            errors.append("密码不能少于 8 个字符")
        if len(self.password) > 128:
            errors.append("密码不能超过 128 个字符")
        if not any(char.isalpha() for char in self.password):
            errors.append("密码必须包含至少一个字母")
        if not any(char.isdigit() for char in self.password):
            errors.append("密码必须包含至少一个数字")
        return errors

    def check_confirm_password(self) -> List[str]:
        """检查确认密码是否与 password 一致。

        返回：
            错误消息列表。列表为空表示确认密码正确。
        """
        if not isinstance(self.confirm_password, str):
            return ["confirm_password 必须是字符串"]
        if self.confirm_password != self.password:
            return ["两次输入的密码不一致"]
        return []

    def check_all(self) -> List[str]:
        """汇总注册请求的业务校验错误。

        返回：
            错误消息列表。列表为空表示注册请求通过业务校验。
        """
        errors = []
        errors.extend(self.check_password())
        errors.extend(self.check_confirm_password())
        return errors


class UserLoginRequest(BaseModel):
    """用户登录接口的请求体。

    字段：
        email：用户邮箱。
        password：明文登录密码。
    """

    email: str
    password: str


class TokenResponse(BaseModel):
    """认证成功后的令牌响应。

    字段：
        access_token：JWT 访问令牌。
        token_type：令牌类型，固定为 bearer。
        user：当前登录用户的公开信息。
    """

    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ProjectCreateRequest(BaseModel):
    """创建项目接口的请求体。

    字段：
        user_id：项目所属用户 id。
        name：项目名称。
        model_graph：前端画布生成的模型图，云端只负责保存。
        description：项目描述，可选。
    """

    user_id: str
    name: str
    model_graph: CloudModelGraph
    description: Optional[str] = None


class ProjectTemplateCreateRequest(BaseModel):
    """基于内置模板创建项目的请求体。

    字段：
        user_id：项目所属用户 id。
        template_name：模板 key 或别名。
        name：项目名称，可选；为空时使用模板生成默认名称。
        description：项目描述，可选。
    """

    user_id: str
    template_name: str
    name: Optional[str] = None
    description: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    """更新项目接口的请求体。

    字段：
        name：新的项目名称，可选。
        model_graph：新的模型图，可选。
        description：新的项目描述，可选。
    """

    name: Optional[str] = None
    model_graph: Optional[CloudModelGraph] = None
    description: Optional[str] = None
