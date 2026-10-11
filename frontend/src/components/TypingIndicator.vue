<script setup lang="ts">
/**
 * 等待首个字出现时的占位动画。
 *
 * 心理场景下"说了很沉重的话却一片空白"的等待感特别强，
 * 所以即使还没有任何 delta 到达，也要给出"正在听"的视觉反馈。
 */

withDefaults(defineProps<{ label?: string; visible?: boolean }>(), {
  label: '正在整理回应…',
  visible: true,
})
</script>

<template>
  <div v-if="visible" class="typing" role="status" aria-live="polite">
    <span class="dots" aria-hidden="true">
      <i /><i /><i />
    </span>
    <span class="psy-hint">{{ label }}</span>
  </div>
</template>

<style scoped>
.typing {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 4px 0;
}

.dots {
  display: inline-flex;
  gap: 4px;
}

.dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--psy-primary);
  opacity: 0.4;
  animation: psy-blink 1.2s infinite ease-in-out;
}

.dots i:nth-child(2) {
  animation-delay: 0.2s;
}

.dots i:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes psy-blink {
  0%,
  80%,
  100% {
    opacity: 0.25;
  }
  40% {
    opacity: 1;
  }
}
</style>

