'''
负责处理“图”的拓扑逻辑，将积木连线转换为代码或可执行顺序
'''

class GraphCompiler:
    def validate_topology(self, graph: GraphSchema):
        """
        检查图是否有环、是否有孤立节点、入口（Input）和出口（Output）是否完整。
        """
        pass

    def infer_shapes(self, graph: GraphSchema):
        """
        从输入层开始，逐层推算 Tensor 的 Shape。
        如果发生维度不匹配（如 128x128 连到了只能接收 64x64 的层），在此抛出错误。
        """
        pass

    def topological_sort(self, graph: GraphSchema):
        """
        对节点进行排序，确保计算时先算前层，再算后层。
        """
        pass

    def generate_python_code(self, graph: GraphSchema):
        """
        核心 API：根据图结构生成标准的 PyTorch .py 源代码文件字符串。
        """
        pass