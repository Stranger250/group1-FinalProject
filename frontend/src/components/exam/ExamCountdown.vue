<template>
  <div class="exam-countdown" :class="{ warn }">
    <el-progress
      v-if="total > 0"
      type="circle"
      :percentage="percentage"
      :width="64"
      :stroke-width="6"
      :color="warn ? 'var(--el-color-danger)' : 'var(--el-color-primary)'"
    >
      <template #default>
        <div class="time" :class="{ warn }">{{ display }}</div>
      </template>
    </el-progress>
    <div v-else class="time-plain" :class="{ warn }">
      <el-icon :size="16"><Clock /></el-icon>
      <span>{{ display }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { formatSeconds } from '@/utils/format'

/**
 * 考试倒计时（本地 1s 递减）。
 * - 以 props.seconds（服务端 remaining_seconds 权威值）为初始值；
 * - 父级每次 save/switch/resume 响应返回新 remaining_seconds 时更新 props，自动校正；
 * - 归零时 emit('finish') 并停止计时，由父级处理自动交卷。
 */
const props = withDefaults(
  defineProps<{
    /** 权威剩余秒数（服务端） */
    seconds: number
    /** 总时长（秒），用于环形进度；<=0 时只显示时间 */
    total?: number
    /** 低于该秒数进入红色预警 */
    warnSeconds?: number
  }>(),
  {
    total: 0,
    warnSeconds: 300,
  },
)

const emit = defineEmits<{ finish: [] }>()

const count = ref(props.seconds)
let timer: number | null = null

const display = computed(() => formatSeconds(count.value))
const warn = computed(() => count.value > 0 && count.value <= props.warnSeconds)
const percentage = computed(() => {
  if (props.total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((count.value / props.total) * 100)))
})

function tick() {
  count.value -= 1
  if (count.value <= 0) {
    count.value = 0
    stop()
    emit('finish')
  }
}

function start() {
  stop()
  timer = window.setInterval(tick, 1000)
}

function stop() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

/** 服务端校正：remaining_seconds 变化即重置本地计数（以服务端为准） */
watch(
  () => props.seconds,
  (v) => {
    count.value = v
  },
)

/** 显式校正（供父级 ref 调用） */
function sync(seconds: number) {
  count.value = seconds
}

onMounted(() => {
  count.value = props.seconds
  start()
})

onBeforeUnmount(stop)

defineExpose({ sync })
</script>

<style scoped>
.exam-countdown {
  display: inline-flex;
  align-items: center;
}

.time {
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.time.warn {
  color: var(--el-color-danger);
  animation: blink 1s steps(2, start) infinite;
}

.time-plain {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: 16px;
  background: var(--brand-soft);
  color: var(--el-color-primary);
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.time-plain.warn {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  50% {
    opacity: 0.55;
  }
}
</style>
