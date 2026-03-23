'''
在模型运行时，把“内部器官”的情况抓取出来发给前端。
'''

class MonitorService:
    def register_hooks(self, model):
        """
        给 PyTorch 模型注册 Forward Hook，以便抓取中间层的输出特征图（Activation）。
        """
        pass

    def get_realtime_metrics(self, trainer_state):
        """
        获取当前的 Loss, Accuracy, Step 等数据，并格式化为前端可读的 JSON。
        """
        pass

    def get_attention_maps(self, model):
        """
        专门针对大模型，提取 Transformer 层的 Attention 权重矩阵。
        """
        pass