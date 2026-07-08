<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { saveProject } from "../actions";
import { activeCanvas, showToast, ui } from "../store";

const form = reactive({ name: "", description: "" });
const saving = ref(false);

// 打开时用当前画布名作为默认项目名
watch(
  () => ui.saveModalOpen,
  open => {
    if (open) {
      form.name = activeCanvas().name || "未命名模型";
      form.description = "";
      saving.value = false;
    }
  }
);

function close() {
  ui.saveModalOpen = false;
}

async function submit() {
  const name = form.name.trim();
  if (!name) {
    showToast("warning", "请输入模型名称。");
    return;
  }
  saving.value = true;
  const ok = await saveProject(name, form.description.trim());
  saving.value = false;
  if (ok) close();
}
</script>

<template>
  <div class="modal" :class="{ hidden: !ui.saveModalOpen }" id="save-modal">
    <div class="modal-card save-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:content-save-outline"></iconify-icon>
          <div>
            <h2>保存模型</h2>
            <p>把当前画布上的模型保存到「我的项目」，之后可随时加载</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-save" @click="close"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>

      <div class="save-body">
        <label class="form-field">
          <span>模型名称</span>
          <input id="save-name" type="text" v-model="form.name" maxlength="60" placeholder="给这个项目起个名字，方便日后查找" @keydown.enter="submit">
        </label>
        <label class="form-field">
          <span>描述（可选）</span>
          <textarea id="save-desc" v-model="form.description" rows="3" maxlength="200" placeholder="记录这个模型的用途、结构要点等"></textarea>
        </label>
      </div>

      <div class="modal-footer">
        <button class="text-button" @click="close">取消</button>
        <button class="primary-button" id="btn-save-submit" :disabled="saving" @click="submit">
          <iconify-icon v-if="saving" icon="mdi:loading" class="spin"></iconify-icon>
          <iconify-icon v-else icon="mdi:content-save-outline"></iconify-icon>
          {{ saving ? "保存中..." : "保存" }}
        </button>
      </div>
    </div>
  </div>
</template>
