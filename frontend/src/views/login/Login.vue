<template>
  <div class="login-page">
    <!-- 左侧：蜀道山水意境（山脊剪影 + 栈道 + 印章） -->
    <div class="login-scene">
      <div class="scene-inner">
        <div class="seal" aria-hidden="true">蜀<br />道</div>
        <h1 class="scene-title brand-font">蜀道安全助手</h1>
        <p class="scene-sub">山路千重 · 安全为纲</p>
        <p class="scene-desc">
          隐患上报 · 法规问答 · 考试工坊<br />
          一条贯通现场、知识与培训的蜀道
        </p>
        <svg class="mountains" viewBox="0 0 640 320" preserveAspectRatio="none" aria-hidden="true">
          <path d="M0 320 L60 210 L120 268 L180 160 L240 240 L300 130 L360 230 L420 175 L480 260 L540 200 L600 250 L640 225 L640 320 Z" class="ridge back" />
          <path d="M0 320 L80 250 L150 300 L230 230 L310 290 L390 250 L470 300 L560 260 L640 290 L640 320 Z" class="ridge front" />
        </svg>
        <div class="scene-motto">
          <span class="motto-line">—— 蜀道之难，难于上青天 ——</span>
        </div>
      </div>
    </div>

    <!-- 右侧：登录表单（暖纸浮卡） -->
    <div class="login-panel">
      <div class="login-card">
        <div class="card-head">
          <span class="card-stamp">登 录</span>
          <p class="card-sub">请用企业账号进入系统</p>
        </div>

        <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" size="large" @keyup.enter="onLogin">
          <el-form-item prop="username">
            <el-input v-model="loginForm.username" placeholder="用户名" :prefix-icon="User" clearable />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="loginForm.password" type="password" placeholder="密码" :prefix-icon="Lock" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" class="login-btn" :loading="loading" @click="onLogin">进 入 系 统</el-button>
          </el-form-item>
        </el-form>

        <div class="login-footer">
          <span>还没有账号？</span>
          <el-link type="primary" @click="registerVisible = true">立即注册</el-link>
        </div>
      </div>
      <div class="panel-foot">蜀道集团 · 安全生产数字化平台</div>
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
}

/* ===== 左屏：蜀道山水 ===== */
.login-scene {
  flex: 1.15;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(900px 520px at 18% 12%, rgba(120, 170, 160, 0.22), transparent 60%),
    linear-gradient(168deg, #0b1d1b 0%, #12302c 55%, #1a433c 100%);
}
.scene-inner {
  position: relative;
  height: 100%;
  padding: 56px 60px;
  display: flex;
  flex-direction: column;
}
/* 印章 */
.seal {
  position: absolute;
  top: 44px;
  right: 52px;
  width: 58px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-serif);
  font-size: 20px;
  line-height: 1.25;
  letter-spacing: 0.05em;
  color: #fdf6ec;
  background: var(--cinnabar);
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  opacity: 0.92;
}
.scene-title {
  margin: 20px 0 10px;
  font-size: 44px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #f4efe2;
}
.scene-sub {
  margin: 0 0 26px;
  font-family: var(--font-serif);
  font-size: 16px;
  letter-spacing: 0.4em;
  color: #b9cdc7;
}
.scene-desc {
  margin: 0;
  font-size: 14px;
  line-height: 2;
  letter-spacing: 0.1em;
  color: #7fa09a;
}
/* 山脊剪影 */
.mountains {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 46%;
}
.ridge.back {
  fill: #12302b;
  opacity: 0.85;
}
.ridge.front {
  fill: #0a1d1a;
}
.scene-motto {
  position: absolute;
  left: 60px;
  bottom: 56px;
}
.motto-line {
  font-family: var(--font-serif);
  font-size: 14px;
  letter-spacing: 0.24em;
  color: #5d7d77;
}

/* ===== 右屏：登录纸卡 ===== */
.login-panel {
  flex: 0.85;
  min-width: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--paper-deep);
  background-image:
    radial-gradient(600px 380px at 85% 8%, rgba(196, 135, 46, 0.08), transparent 60%),
    radial-gradient(500px 420px at 8% 92%, rgba(30, 90, 82, 0.06), transparent 60%);
}
.login-card {
  width: 380px;
  padding: 38px 34px 26px;
  background: var(--paper);
  border: 1px solid var(--el-border-color-lighter);
  border-top: 3px solid var(--brand);
  border-radius: 6px;
  box-shadow: var(--shadow-card);
}
.card-head {
  margin-bottom: 26px;
}
.card-stamp {
  display: inline-block;
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: var(--ink);
  padding-bottom: 10px;
  border-bottom: 2px solid var(--brand);
}
.card-sub {
  margin: 12px 0 0;
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--el-text-color-secondary);
}
.login-btn {
  width: 100%;
  letter-spacing: 0.3em;
  font-weight: 600;
}
.login-footer {
  margin-top: 14px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.panel-foot {
  position: absolute;
  bottom: 24px;
  font-size: 12px;
  letter-spacing: 0.14em;
  color: var(--el-text-color-placeholder);
}

@media (max-width: 900px) {
  .login-scene {
    display: none;
  }
  .login-panel {
    flex: 1;
    min-width: 0;
  }
}
</style>
