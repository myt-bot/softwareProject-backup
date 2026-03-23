'''
负责加载数据，并将其转化为 PyTorch 能够识别的 DataLoader
'''

class DataManager:
    def load_dataset_provider(self, source_type, path):
        """
        读取本地文件（CSV/Images）或调用内置数据集（MNIST/CIFAR）。
        """
        pass

    def build_pipeline(self, preprocess_config):
        """
        构建数据预处理流（Resize, Normalization, Tokenization）。
        """
        pass

    def get_dataloader(self, dataset, batch_size):
        """
        封装成 PyTorch 的 DataLoader 对象，支持多线程读取。
        """
        pass