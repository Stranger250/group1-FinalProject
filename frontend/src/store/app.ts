import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', () => {
  /** 侧栏是否折叠 */
  const collapsed = ref(false)

  function toggleCollapse(): void {
    collapsed.value = !collapsed.value
  }

  return { collapsed, toggleCollapse }
})
