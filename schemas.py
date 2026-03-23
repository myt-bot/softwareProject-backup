'''
定义前端传来的JSON数据的格式，确保数据在进入逻辑层前是合法的
'''

# 定义单个积木节点的配置格式
class NodeSchema:
    """
    包括节点ID、类型(Conv2d/Linear)、位置、以及参数字典(kernel_size等)
    """
    pass

# 定义节点间的连线格式
class EdgeSchema:
    """
    包括源节点ID、目标节点ID、连接端口索引
    """
    pass

# 整个图的定义
class GraphSchema:
    """
    包含 nodes 列表和 edges 列表
    """
    pass