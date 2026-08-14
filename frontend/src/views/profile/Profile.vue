<template>
  <div class="page-container profile-wrap">
    <el-card shadow="never" class="profile-card">
      <template #header>
        <div class="card-title">基本信息</div>
      </template>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px" class="profile-form">
        <el-form-item label="头像">
          <el-upload
            class="avatar-uploader"
            :show-file-list="false"
            :http-request="onAvatarUpload"
            accept=".jpg,.jpeg,.png"
            :before-upload="beforeAvatarUpload"
          >
            <el-avatar :size="72" class="avatar-preview" :src="form.avatar || undefined">
              {{ (form.name || '?').slice(0, 1) }}
            </el-avatar>
            <div class="avatar-tip">点击更换（jpg/png，≤5MB）</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input :model-value="userStore.user?.username" disabled />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" maxlength="64" placeholder="请输入姓名" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" maxlength="20" placeholder="选填" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" maxlength="120" placeholder="选填" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveProfile">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="profile-card">
      <template #header>
        <div class="card-title">修改密码</div>
      </template>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px" class="profile-form">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="6-64 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="pwdForm.confirm" type="password" show-password placeholder="再次输入新密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="changing" @click="changePassword">确认修改</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { changePasswordApi, updateProfileApi, uploadAvatarApi } from '@/api/auth'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

// ---------- 基本信息 ----------
const formRef = ref<FormInstance>()
const form = reactive({
  name: userStore.user?.name ?? '',
  phone: userStore.user?.phone ?? '',
  email: userStore.user?.email ?? '',
  avatar: userStore.user?.avatar ?? '',
})
const saving = ref(false)

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  phone: [
    {
      validator: (_r, v: string, cb) => {
        if (v && !/^\d+$/.test(v)) cb(new Error('手机号只能包含数字'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
  email: [
    {
      validator: (_r, v: string, cb) => {
        if (v && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) cb(new Error('邮箱格式不正确'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
})

async function saveProfile(): Promise<void> {
  const ok = await formRef.value?.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const user = await updateProfileApi({
      name: form.name.trim(),
      phone: form.phone.trim() || null,
      email: form.email.trim() || null,
    })
    form.avatar = user.avatar ?? ''
    userStore.setUser(user)
    ElMessage.success('资料已保存')
  } catch {
    // 后端 message 已提示
  } finally {
    saving.value = false
  }
}

// ---------- 头像上传 ----------
function beforeAvatarUpload(file: File): boolean {
  const okType = ['image/jpeg', 'image/png'].includes(file.type)
  if (!okType) {
    ElMessage.error('仅支持 jpg/png 图片')
    return false
  }
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('图片不能超过 5MB')
    return false
  }
  return true
}

async function onAvatarUpload(options: { file: File }): Promise<void> {
  try {
    const user = await uploadAvatarApi(options.file)
    form.avatar = user.avatar ?? ''
    userStore.setUser(user)
    ElMessage.success('头像已更新')
  } catch {
    // 后端 message 已提示
  }
}

// ---------- 修改密码 ----------
const pwdFormRef = ref<FormInstance>()
const pwdForm = reactive({ old_password: '', new_password: '', confirm: '' })
const changing = ref(false)

const pwdRules = reactive<FormRules>({
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度为 6-64 位', trigger: 'blur' },
  ],
  confirm: [
    {
      validator: (_r, v: string, cb) => {
        if (!v) cb(new Error('请再次输入新密码'))
        else if (v !== pwdForm.new_password) cb(new Error('两次输入的密码不一致'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
})

async function changePassword(): Promise<void> {
  const ok = await pwdFormRef.value?.validate().catch(() => false)
  if (!ok) return
  changing.value = true
  try {
    await changePasswordApi({ old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码已修改，下次登录请使用新密码')
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm = ''
    pwdFormRef.value?.clearValidate()
  } catch {
    // 后端 message 已提示（如原密码不正确）
  } finally {
    changing.value = false
  }
}
</script>

<style scoped>
.profile-wrap {
  max-width: 720px;
}
.profile-card {
  margin-bottom: 12px;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.profile-form {
  max-width: 460px;
}
.avatar-uploader {
  cursor: pointer;
}
.avatar-preview {
  background-color: var(--el-color-primary, #1e5a52);
  color: #fff;
  font-size: 26px;
}
.avatar-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
