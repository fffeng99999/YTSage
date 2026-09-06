<template>
  <div class="setup-container">
    <div class="setup-box">
      <div class="logo">
        <el-icon :size="42" color="#c90000"><VideoCamera /></el-icon>
        <h1>YTSage</h1>
        <p>{{ t('web.setup_title') }}</p>
      </div>

      <el-steps :active="step" align-center finish-status="success" style="margin-bottom: 24px">
        <el-step :title="t('web.setup_step1')" />
        <el-step :title="t('web.setup_step2')" />
        <el-step :title="t('web.setup_step3')" />
      </el-steps>

      <!-- Step 1: language -->
      <div v-if="step === 0">
        <p class="desc">{{ t('web.setup_lang_desc') }}</p>
        <el-radio-group v-model="form.language" size="large">
          <el-radio-button value="en">English</el-radio-button>
          <el-radio-button value="zh">中文</el-radio-button>
        </el-radio-group>
        <div class="nav">
          <el-button type="primary" @click="step = 1">{{ t('web.setup_next') }}</el-button>
        </div>
      </div>

      <!-- Step 2: password -->
      <div v-else-if="step === 1">
        <p class="desc">{{ t('web.setup_pwd_desc') }}</p>
        <el-form label-position="top">
          <el-form-item :label="t('web.new_password')">
            <el-input v-model="form.password" type="password" show-password size="large" />
          </el-form-item>
          <el-form-item :label="t('web.confirm_password')">
            <el-input v-model="form.confirm_password" type="password" show-password size="large" @keyup.enter="nextFromPwd" />
          </el-form-item>
        </el-form>
        <div class="nav">
          <el-button @click="step = 0">{{ t('web.setup_back') }}</el-button>
          <el-button type="primary" @click="nextFromPwd">{{ t('web.setup_next') }}</el-button>
        </div>
      </div>

      <!-- Step 3: config mode + path -->
      <div v-else>
        <p class="desc">{{ t('web.setup_mode_desc') }}</p>
        <el-radio-group v-model="form.mode" style="margin-bottom: 16px">
          <div class="mode-opt">
            <el-radio value="standalone">
              <b>{{ t('web.setup_mode_standalone') }}</b>
            </el-radio>
            <p class="mode-help">{{ t('web.setup_mode_standalone_help') }}</p>
          </div>
          <div class="mode-opt" v-if="defaults.desktop_config_available">
            <el-radio value="shared">
              <b>{{ t('web.setup_mode_shared') }}</b>
            </el-radio>
            <p class="mode-help">{{ t('web.setup_mode_shared_help') }}</p>
          </div>
        </el-radio-group>

        <div class="mode-opt" v-if="form.mode === 'standalone' && defaults.desktop_config_available">
          <el-checkbox v-model="form.import_desktop">{{ t('web.setup_import') }}</el-checkbox>
        </div>

        <el-form label-position="top" style="margin-top: 8px">
          <el-form-item :label="t('settings.download_path')">
            <el-input v-model="form.download_path" size="large" :placeholder="defaults.download_path" />
          </el-form-item>
        </el-form>

        <div class="nav">
          <el-button @click="step = 1">{{ t('web.setup_back') }}</el-button>
          <el-button type="primary" :loading="finishing" @click="finish">{{ t('web.setup_finish') }}</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { VideoCamera } from '@element-plus/icons-vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { loadLocale } from '@/i18n'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()

const step = ref(0)
const finishing = ref(false)
const defaults = ref({ desktop_config_available: false, download_path: '', language: 'en' })

const form = reactive({
  language: 'en',
  password: '',
  confirm_password: '',
  mode: 'standalone',
  download_path: '',
  import_desktop: false,
})

function nextFromPwd() {
  if (form.password.length < 4) return ElMessage.error(t('web.password_too_short'))
  if (form.password !== form.confirm_password) return ElMessage.error(t('web.passwords_mismatch'))
  step.value = 2
}

async function finish() {
  finishing.value = true
  try {
    const { data } = await axios.post('/api/setup/complete', {
      password: form.password,
      mode: form.mode,
      download_path: form.download_path || null,
      language: form.language,
      import_desktop: form.import_desktop,
    })
    localStorage.setItem('ytsage_setup_done', '1')
    authStore.token = data.token
    localStorage.setItem('ytsage_token', data.token)
    await loadLocale(form.language)
    router.replace('/')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'setup failed')
  } finally {
    finishing.value = false
  }
}

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/setup/defaults')
    defaults.value = data
    form.language = data.language || 'en'
    form.download_path = data.download_path || ''
  } catch {}
})
</script>

<style scoped>
.setup-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at top, #1d2426 0%, #15181b 60%);
  padding: 20px;
}
.setup-box {
  width: 640px;
  max-width: 100%;
  padding: 36px 40px;
  background: var(--yts-panel, #1b2021);
  border: 1px solid var(--yts-border, #3d3d3d);
  border-radius: 12px;
}
.logo { text-align: center; margin-bottom: 20px; }
.logo h1 { margin: 8px 0 4px; font-size: 26px; color: #fff; }
.logo p { margin: 0; color: #909399; font-size: 14px; }
.desc { color: var(--yts-text-dim); font-size: 14px; }
.nav { margin-top: 24px; display: flex; justify-content: flex-end; gap: 10px; }
.mode-opt { margin-bottom: 6px; }
.mode-help { color: var(--yts-text-dim); font-size: 12px; margin: 2px 0 0 24px; }
:deep(.el-step__title) { font-size: 13px; }
</style>
