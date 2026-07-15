<script setup lang="ts">
import { closeHelpModal, ui } from "../store";
</script>

<template>
  <!-- 新手指南弹窗 -->
  <div class="modal" :class="{ hidden: !ui.helpModalOpen }" id="help-modal">
    <div class="modal-card help-card">
      <div class="modal-header">
        <div class="modal-title">
          <iconify-icon icon="mdi:school-outline"></iconify-icon>
          <div>
            <h2>欢迎来到模型工坊 👋</h2>
            <p>不用写一行代码，像搭积木一样搭建你的第一个神经网络</p>
          </div>
        </div>
        <button class="icon-button" id="btn-close-help" @click="closeHelpModal"><iconify-icon icon="mdi:close"></iconify-icon></button>
      </div>
      <div class="help-body">
        <div class="help-steps">
          <div class="help-step">
            <span class="help-step-num">1</span>
            <h3>添加组件</h3>
            <p>单击左侧模型层可自动添加到画布，也可以把它拖到画布中的指定位置。</p>
          </div>
          <div class="help-step">
            <span class="help-step-num">2</span>
            <h3>连接节点</h3>
            <p>在节点上点击右键，选择“进行连线”，再点击目标节点，数据就会沿着连线流动。</p>
          </div>
          <div class="help-step">
            <span class="help-step-num">3</span>
            <h3>检查结构</h3>
            <p>点击底部“检查结构”，系统会自动检查每一层的尺寸是否匹配，出错时会给出修复提示。</p>
          </div>
          <div class="help-step">
            <span class="help-step-num">4</span>
            <h3>开始训练</h3>
            <p>检查通过后点击“开始训练”，实时观看损失下降、准确率上升的全过程。</p>
          </div>
        </div>
        <div class="help-tips">
          <h3><iconify-icon icon="mdi:lightbulb-on-outline"></iconify-icon>实用小技巧</h3>
          <ul>
            <li><b>单击节点</b>：选中节点，在右侧面板查看和修改参数</li>
            <li><b>复制节点</b>：选中后使用悬浮工具条、右键菜单或 Ctrl+C，再按 Ctrl+V 粘贴</li>
            <li><b>快速删除</b>：选中节点或连线后，按 Delete / Backspace 即可删除</li>
            <li><b>教学辅助</b>：打开工作区右下角的“教学辅助”，可查看当前层作用、参数说明、模型概览和结构错误修改指导</li>
            <li><b>拖动节点</b>：按住节点移动，调整画布布局</li>
            <li><b>右键操作</b>：节点可连线、复制或删除，连线可直接删除</li>
            <li><b>快速开始</b>：不知道从哪下手？点画布上方的“快速开始模板”，从模板库一键加载现成的经典网络结构</li>
            <li><b>换数据集</b>：顶部可切换不同的训练数据集</li>
            <li><b>导出代码</b>：搭好的模型可一键导出为 PyTorch 代码，边玩边学</li>
          </ul>
        </div>
      </div>
      <div class="modal-footer">
        <button class="primary-button" id="btn-start-building" @click="closeHelpModal">
          <iconify-icon icon="mdi:rocket-launch-outline"></iconify-icon>
          我知道了，开始搭建
        </button>
      </div>
    </div>
  </div>
</template>
