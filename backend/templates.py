"""内置入门模型模板。"""


def get_available_templates():
    """返回前端可选择的模型模板，例如 MLP 和 CNN。

    参数：
        无。

    返回：
        后续应返回模板名称、说明和适用任务等信息列表。
    """
    pass


def create_mlp_template():
    """创建适合初学者使用的 MLP 模板图。

    参数：
        无。

    返回：
        后续应返回符合 ModelGraph 结构的 MLP 模板数据。
    """
    pass


def create_cnn_template():
    """创建适合图像分类任务的入门 CNN 模板图。

    参数：
        无。

    返回：
        后续应返回符合 ModelGraph 结构的 CNN 模板数据。
    """
    pass


def apply_template(template_name):
    """返回用户选择的模板图，供前端加载到画布中。

    参数：
        template_name：用户选择的模板名称，例如 "MLP" 或 "CNN"。

    返回：
        后续应返回对应模板的模型图结构；模板不存在时返回错误信息。
    """
    pass
