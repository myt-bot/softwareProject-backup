"""本地 PyTorch 训练流程。"""


def create_training_job(model_graph, train_config):
    """在训练开始前创建并登记一个训练任务。"""
    pass


def run_training_job(job_id):
    """执行一个已登记训练任务的完整训练流程。"""
    pass


def prepare_dataset(dataset_name, batch_size):
    """加载并预处理用户选择的内置数据集。"""
    pass


def train_one_epoch(model, train_loader, optimizer, loss_fn, device):
    """训练一个 epoch，并返回该轮训练指标。"""
    pass


def evaluate_model(model, test_loader, loss_fn, device):
    """评估模型，并返回验证损失和准确率。"""
    pass


def save_training_artifacts(job_id, model, metrics):
    """保存训练产生的模型权重、指标和日志。"""
    pass


def get_job_status(job_id):
    """返回训练任务的当前状态和进度。"""
    pass


def get_job_result(job_id):
    """返回已完成训练任务的最终指标和保存文件路径。"""
    pass


def stop_training_job(job_id):
    """请求取消一个正在运行的训练任务。"""
    pass
