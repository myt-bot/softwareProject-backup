<script setup lang="ts">
import { computed } from "vue";
import { activeCanvas, showToast, store, ui } from "../store";
import SelectField from "./SelectField.vue";

const canvas = computed(() => activeCanvas());

const MAX_EPOCHS = 100;

// 与后端 _build_optimizer / _build_loss_fn 支持的取值一一对应
const OPTIMIZERS = [
  { value: "sgd", label: "SGD（随机梯度下降，稳健）" },
  { value: "adam", label: "Adam（自适应，收敛快，最常用）" },
  { value: "adamw", label: "AdamW（Adam + 权重衰减，泛化更好）" },
  { value: "rmsprop", label: "RMSprop（自适应学习率）" },
  { value: "adagrad", label: "Adagrad（累积梯度自适应）" },
  { value: "adadelta", label: "Adadelta（无需手调学习率）" },
];
const LOSSES = [
  { value: "cross_entropy", label: "交叉熵 Cross Entropy（分类首选）" },
  { value: "nll", label: "负对数似然 NLL（配合 LogSoftmax 的分类损失）" },
  { value: "mse", label: "均方误差 MSE（回归常用）" },
  { value: "l1", label: "平均绝对误差 L1 / MAE（回归，对异常值更稳）" },
  { value: "smooth_l1", label: "平滑 L1 / Huber（介于 MSE 与 L1 之间）" },
];

function setEpochs(event: Event) {
  const raw = Math.round(Number((event.target as HTMLInputElement).value));
  if (!Number.isFinite(raw) || raw < 1) {
    showToast("warning", `训练轮次须为 1-${MAX_EPOCHS} 的整数。`);
    canvas.value.epochs = 1;
    return;
  }
  canvas.value.epochs = Math.min(raw, MAX_EPOCHS);
}

function setBatchSize(event: Event) {
  const raw = Math.round(Number((event.target as HTMLInputElement).value));
  if (!Number.isFinite(raw) || raw < 1) {
    showToast("warning", "批大小须为正整数（常用 32 / 64 / 128）。");
    store.batchSize = 64;
    return;
  }
  store.batchSize = Math.min(raw, 4096);
}

function setLearningRate(event: Event) {
  const raw = Number((event.target as HTMLInputElement).value);
  if (!Number.isFinite(raw) || raw <= 0) {
    showToast("warning", "学习率须为正数（常用 0.1 ~ 0.0001）。");
    store.learningRate = 0.001;
    return;
  }
  store.learningRate = raw;
}

function restoreDefaults() {
  canvas.value.epochs = 1;
  store.batchSize = 64;
  store.learningRate = 0.001;
  store.optimizer = "sgd";
  store.lossFn = "cross_entropy";
  showToast("info", "训练超参数已恢复默认。");
}
</script>

<template>
  <div class="modal" :class="{ hidden: !ui.trainSettingsOpen }" id="train-settings">
    <div class="modal-card train-settings-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:tune-variant"></iconify-icon>
          <div>
            <h2>训练超参数 Hyperparameters</h2>
            <p>调整训练方式；改动会用于下一次「开始训练」。</p>
          </div>
        </div>
        <button class="icon-button" @click="ui.trainSettingsOpen = false">
          <iconify-icon icon="mdi:close"></iconify-icon>
        </button>
      </div>

      <div class="train-settings-body">
        <label class="form-field">
          <span>训练轮次 epochs</span>
          <input type="number" min="1" :max="MAX_EPOCHS" :value="canvas.epochs" @change="setEpochs">
          <small>整个训练集完整过一遍算一轮；越多学得越充分，但更慢、易过拟合。</small>
        </label>

        <label class="form-field">
          <span>批大小 batch size</span>
          <input type="number" min="1" step="1" :value="store.batchSize" @change="setBatchSize">
          <small>每次喂给模型的样本数；越大越快但更吃显存，常用 32 / 64 / 128。</small>
        </label>

        <label class="form-field">
          <span>学习率 learning rate</span>
          <input type="number" min="0" step="0.0001" :value="store.learningRate" @change="setLearningRate">
          <small>每步参数更新的幅度；过大不收敛、过小太慢，常用 0.1 ~ 0.0001。</small>
        </label>

        <div class="form-field">
          <span>优化器 optimizer</span>
          <SelectField v-model="store.optimizer" :options="OPTIMIZERS" />
          <small>更新参数所用的算法。</small>
        </div>

        <div class="form-field train-settings-loss">
          <span>损失函数 loss</span>
          <SelectField v-model="store.lossFn" :options="LOSSES" />
          <small>衡量预测与正确答案差距的函数；分类任务通常用交叉熵。</small>
        </div>
      </div>

      <div class="modal-footer">
        <button class="text-button" @click="restoreDefaults">恢复默认</button>
        <button class="primary-button" @click="ui.trainSettingsOpen = false">
          <iconify-icon icon="mdi:check"></iconify-icon>
          完成
        </button>
      </div>
    </div>
  </div>
</template>
