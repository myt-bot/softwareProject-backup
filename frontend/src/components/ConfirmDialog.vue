<script setup lang="ts">
import { confirmDialog, resolveConfirm } from "../store";
</script>

<template>
  <div class="modal confirm-modal" :class="{ hidden: !confirmDialog.open }" @click.self="resolveConfirm('cancel')">
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
        <button type="button" class="confirm-cancel" @click="resolveConfirm('cancel')">
          {{ confirmDialog.cancelText }}<kbd v-if="confirmDialog.denyText" class="confirm-key">Esc</kbd>
        </button>
        <button v-if="confirmDialog.denyText" type="button" class="confirm-deny" @click="resolveConfirm('deny')">
          {{ confirmDialog.denyText }}<kbd class="confirm-key">N</kbd>
        </button>
        <button type="button" class="confirm-ok" :class="{ danger: confirmDialog.danger }" @click="resolveConfirm('confirm')">
          {{ confirmDialog.confirmText }}<kbd v-if="confirmDialog.denyText" class="confirm-key on-primary">S</kbd>
        </button>
      </div>
    </div>
  </div>
</template>
