<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <el-icon :size="40" class="login-logo"><Umbrella /></el-icon>
        <h1 class="brand-font">蜀道安全助手</h1>
        <p>隐患上报 · 法规问答 · 在线考试</p>
      </div>

      <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" size="large" @keyup.enter="onLogin">
        <el-form-item prop="username">
          <el-input v-model="loginForm.username" placeholder="用户名" :prefix-icon="User" clearable />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="密码" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" class="login-btn" :loading="loading" @click="onLogin">登 录</el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <span>还没有账号？</span>
        <el-link type="primary" @click="registerVisible = true">立即注册</el-link>
      </div>
    </div>

    <el-dialog v-model="registerVisible" title="注册账号" width="420px" append-to-body>
      <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" label-width="72px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="registerForm.username" placeholder="3-64 位" clearable />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="registerForm.name" placeholder="真实姓名" clearable />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="registerForm.password" type="password" placeholder="6-64 位" show-password />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm">
          <el-input v-model="registerForm.confirm" type="password" placeholder="再次输入密码" show-password />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="registerForm.phone" placeholder="选填" clearable />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="registerVisible = false">取消</el-button>
        <el-button type="primary" :loading="registerLoading" @click="onRegister">注册</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const loading = ref(false)
const registerVisible = ref(false)
const registerLoading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const registerForm = reactive({ username: '', name: '', password: '', confirm: '', phone: '' })
const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 64, message: '用户名长度 3-64 位', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6-64 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, cb) => {
        if (value !== registerForm.password) cb(new Error('两次输入的密码不一致'))
        else cb()
      },
      trigger: 'blur',
    },
  ],
  phone: [{ pattern: /^1\d{10}$/, message: '手机号格式不正确', trigger: 'blur' }],
}

async function onLogin() {
  const ok = await loginFormRef.value?.validate().catch(() => false)
  if (!ok) return
  loading.value = true
  try {
    const user = await userStore.login(loginForm.username, loginForm.password)
    ElMessage.success(`欢迎回来，${user.name}`)
    const redirect = (route.query.redirect as string) || '/home'
    router.replace(redirect)
  } finally {
    loading.value = false
  }
}

async function onRegister() {
  const ok = await registerFormRef.value?.validate().catch(() => false)
  if (!ok) return
  registerLoading.value = true
  try {
    const user = await userStore.register({
      username: registerForm.username,
      password: registerForm.password,
      name: registerForm.name,
      phone: registerForm.phone || undefined,
    })
    ElMessage.success(`注册成功，请登录：${user.username}`)
    loginForm.username = registerForm.username
    registerVisible.value = false
    registerFormRef.value?.resetFields()
  } finally {
    registerLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 蜀道山黛渐变：青泥底色 + 山脊暗部 + 暖光点缀，替代冷蓝海军渐变 */
  background:
    radial-gradient(1100px 560px at 12% 18%, rgba(90, 150, 140, 0.18), transparent 60%),
    radial-gradient(900px 520px at 88% 88%, rgba(196, 135, 46, 0.12), transparent 60%),
    linear-gradient(160deg, #0a1f1e 0%, #14342f 50%, #1b4740 100%);
}
.login-card {
  width: 400px;
  padding: 40px 36px 24px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter, #ece8df);
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(12, 32, 30, 0.18);
}
.login-header {
  text-align: center;
  margin-bottom: 28px;
}
.login-logo {
  color: var(--el-color-primary, #1e5a52);
}
.login-header h1 {
  font-size: 24px;
  margin: 14px 0 6px;
  color: var(--el-text-color-primary, #232b2a);
}
.login-header p {
  margin: 0;
  color: var(--el-text-color-secondary, #707a78);
  font-size: 13px;
  letter-spacing: 0.02em;
}
.login-btn {
  width: 100%;
}
.login-footer {
  text-align: center;
  color: var(--el-text-color-secondary, #707a78);
  font-size: 13px;
}
</style>
