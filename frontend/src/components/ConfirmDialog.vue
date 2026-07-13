<script setup lang="ts">
import { confirmDialog, resolveConfirm } from "../store";
</script>

<template>
  <div class="modal confirm-modal" :class="{ hidden: !confirmDialog.open }" @click.self="resolveConfirm(false)">
    <div class="modal-card confirm-card">
      <div class="confirm-head">
        <span class="confirm-icon" :class="{ danger: confirmDialog.danger }">
          <iconify-icon :icon="confirmDialog.danger ? 'mdi:alert-outline' : 'mdi:help-circle-outline'"></iconify-icon>
        </span>
        <div class="confirm-copy">
          <h3>{{ confirmDialog.title }}</h3>
          <p>{{ confirmDialog.message }}</p>
        </div>
      </div>
      <div class="confirm-actions">
        <button type="button" class="confirm-cancel" @click="resolveConfirm(false)">{{ confirmDialog.cancelText }}</button>
        <button type="button" class="confirm-ok" :class="{ danger: confirmDialog.danger }" @click="resolveConfirm(true)">{{ confirmDialog.confirmText }}</button>
      </div>
    </div>
  </div>
</template>
