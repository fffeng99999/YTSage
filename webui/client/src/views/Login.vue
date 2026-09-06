<template>
  <div class="login-container">
    <div class="login-box">
      <div class="logo">
        <el-icon :size="48" color="#c90000"><VideoCamera /></el-icon>
        <h1>YTSage</h1>
        <p>Web Control UI</p>
      </div>
      <el-form @submit.prevent="handleLogin" :model="form" :rules="rules" ref="formRef">
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('web.current_password')"
            show-password
            size="large"
            :prefix-icon="Lock"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            style="width: 100%"
            @click="handleLogin"
          >
            Login
          </el-button>
        </el-form-item>
      </el-form>
      <p class="hint">{{ t('web.default_password_hint') }}</p>
      <div class="lang-switch">
        <el-button link size="small" :type="lang === 'zh' ? 'primary' : ''" @click="switchLang('zh')">中文</el-button>
        <el-button link size="small" :type="lang === 'en' ? 'primary' : ''" @click="switchLang('en')">English</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { VideoCamera, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { loadLocale } from '@/i18n'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const lang = ref(locale.value)
const formRef = ref(null)
const loading = ref(false)
const form = ref({ password: '' })
const rules = {
  password: [{ required: true, message: 'password required', trigger: 'blur' }],
}

function switchLang(v) {
  lang.value = v
  loadLocale(v)
}

async function handleLogin() {
  await formRef.value?.validate().catch(() => {})
  const password = (form.value.password || '').trim()
  if (!password) return
  loading.value = true
  try {
    await authStore.login(password)
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    if (e.response?.status === 428) {
      localStorage.removeItem('ytsage_setup_done')
      router.replace('/setup')
      return
    }
    const detail = e.response?.data?.detail
    ElMessage.error(detail === 'Invalid password' ? t('web.login_failed_invalid') : (detail || 'Login failed'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at top, #1d2426 0%, #15181b 60%);
}
.login-box {
  width: 380px;
  padding: 40px 32px;
  background: var(--yts-panel, #1b2021);
  border: 1px solid var(--yts-border, #3d3d3d);
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.logo { text-align: center; margin-bottom: 32px; }
.logo h1 { margin: 12px 0 4px; font-size: 28px; color: #fff; }
.logo p { margin: 0; color: #909399; font-size: 14px; }
.hint { text-align: center; color: #6a6f73; font-size: 12px; margin-top: 16px; }
.hint code { background: #101214; padding: 2px 6px; border-radius: 4px; }
.lang-switch { text-align: center; margin-top: 8px; }
</style>
