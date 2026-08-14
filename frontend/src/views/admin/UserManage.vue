<template>
  <div class="page-container">
    <el-card shadow="never" class="filter-card">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="用户名/姓名"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select v-model="query.role_id" placeholder="角色" clearable style="width: 150px" @change="handleSearch">
          <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 120px" @change="handleSearch">
          <el-option label="启用" :value="1" />
          <el-option label="禁用" :value="0" />
        </el-select>
        <el-button type="primary" :icon="'Search'" @click="handleSearch">查询</el-button>
        <el-button :icon="'Refresh'" @click="handleReset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="pageData?.items ?? []" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="用户" min-width="150">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="28" :src="(row as UserAdminItem).avatar || undefined">
                {{ ((row as UserAdminItem).name || '?').slice(0, 1) }}
              </el-avatar>
              <div class="user-meta">
                <div class="user-name">{{ (row as UserAdminItem).name }}</div>
                <div class="user-username">{{ (row as UserAdminItem).username }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="150">
          <template #default="{ row }">
            <el-select
              :model-value="(row as UserAdminItem).role_id"
              size="small"
              style="width: 126px"
              :disabled="isSelf(row as UserAdminItem)"
              @change="(v: number) => onRoleChange(row as UserAdminItem, v)"
            >
              <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="手机号" width="130">
          <template #default="{ row }">{{ (row as UserAdminItem).phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="160">
          <template #default="{ row }">{{ (row as UserAdminItem).email || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="(row as UserAdminItem).status === 1"
              :disabled="isSelf(row as UserAdminItem)"
              @change="(v: boolean) => onStatusChange(row as UserAdminItem, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ formatDateTime((row as UserAdminItem).created_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button link type="warning" size="small" @click="onResetPassword(row as UserAdminItem)">
              重置密码
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="pageData?.total ?? 0"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          small
          @current-change="load"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listUsers, resetUserPassword, updateUser, type UserQuery } from '@/api/user'
import { useUserStore } from '@/store/user'
import { formatDateTime } from '@/utils/format'
import type { PageResult } from '@/types/api'
import { ROLE, type UserAdminItem } from '@/types/models/user'

const userStore = useUserStore()

const ROLE_OPTIONS = [
  { value: ROLE.EMPLOYEE, label: '普通员工' },
  { value: ROLE.SAFETY, label: '安全管理员' },
  { value: ROLE.ADMIN, label: '系统管理员' },
]

const loading = ref(false)
const pageData = ref<PageResult<UserAdminItem> | null>(null)
const query = reactive<UserQuery>({ keyword: '', role_id: undefined, status: undefined, page: 1, page_size: 20 })

function isSelf(row: UserAdminItem): boolean {
  return row.id === userStore.user?.id
}

async function load(): Promise<void> {
  loading.value = true
  try {
    pageData.value = await listUsers({ ...query })
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  query.page = 1
  void load()
}

function handleReset(): void {
  query.keyword = ''
  query.role_id = undefined
  query.status = undefined
  query.page = 1
  void load()
}

function handleSizeChange(): void {
  query.page = 1
  void load()
}

async function onRoleChange(row: UserAdminItem, roleId: number): Promise<void> {
  if (roleId === row.role_id) return
  try {
    await updateUser(row.id, { role_id: roleId })
    ElMessage.success(`已更新「${row.name}」的角色`)
  } catch {
    void load() // 失败回滚为服务端最新值
  }
}

async function onStatusChange(row: UserAdminItem, enabled: boolean): Promise<void> {
  const status = enabled ? 1 : 0
  const action = enabled ? '启用' : '禁用'
  try {
    await ElMessageBox.confirm(`确定${action}用户「${row.name}」（${row.username}）吗？`, `${action}确认`, {
      type: 'warning',
    })
  } catch {
    void load() // 取消：还原开关状态
    return
  }
  try {
    await updateUser(row.id, { status })
    ElMessage.success(`${action}成功`)
  } catch {
    void load() // 失败（如最后一个管理员）回滚
  }
}

async function onResetPassword(row: UserAdminItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定为「${row.name}」（${row.username}）重置密码？重置后旧密码立即失效。`, '重置密码', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    const res = await resetUserPassword(row.id)
    await ElMessageBox.alert(`请将临时密码告知用户，仅本次展示：\n\n${res.new_password}`, '重置成功', {
      type: 'success',
      confirmButtonText: '我已复制',
    })
  } catch {
    // 后端 message 已提示
  }
}

void load()
</script>

<style scoped>
.filter-card {
  margin-bottom: 12px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.user-meta {
  line-height: 1.3;
}
.user-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.user-username {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
