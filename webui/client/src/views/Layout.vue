<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <el-icon :size="26" color="#c90000"><VideoCamera /></el-icon>
        <span>YTSage</span>
      </div>
      <el-menu :default-active="activeMenu" router class="side-menu">
        <el-menu-item index="/">
          <el-icon><Download /></el-icon>
          <span>{{ t('buttons.download') }}</span>
        </el-menu-item>
        <el-menu-item index="/jobs">
          <el-icon><List /></el-icon>
          <span>{{ t('history.title') === '历史' ? '任务' : 'Jobs' }}</span>
          <el-badge v-if="activeCount > 0" :value="activeCount" class="job-badge" />
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Clock /></el-icon>
          <span>{{ t('history.title') }}</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>{{ t('settings.title') }}</span>
        </el-menu-item>
        <el-menu-item index="/tools">
          <el-icon><Tools /></el-icon>
          <span>{{ t('buttons.custom_options') }}</span>
        </el-menu-item>
        <el-menu-item index="/updater">
          <el-icon><Refresh /></el-icon>
          <span>{{ t('tabs.updater') }}</span>
        </el-menu-item>
        <el-menu-item index="/about">
          <el-icon><InfoFilled /></el-icon>
          <span>{{ t('about.title') }}</span>
        </el-menu-item>
      </el-menu>
      <div class="version-info">
        <el-tag size="small" :type="wsConnected ? 'success' : 'info'">
          {{ wsConnected ? '● Live' : '○ Offline' }}
        </el-tag>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="header-left">
          <h3>{{ pageTitle }}</h3>
        </div>
        <div class="header-right">
          <el-select v-model="lang" size="small" style="width: 100px" @change="switchLang">
            <el-option label="中文" value="zh" />
            <el-option label="EN" value="en" />
          </el-select>
          <el-dropdown @command="handleCommand" style="margin-left: 14px">
            <el-button text>
              <el-icon><UserFilled /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">
                  <el-icon><SwitchButton /></el-icon> Logout
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import {
  VideoCamera, Download, List, Clock, Setting, Tools, Refresh,
  InfoFilled, UserFilled, SwitchButton,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useDownloadStore } from '@/stores/download'
import { useSettingsStore } from '@/stores/settings'
import { loadLocale } from '@/i18n'

const { t, locale } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const downloadStore = useDownloadStore()
const settingsStore = useSettingsStore()

const lang = ref(locale.value)

const activeMenu = computed(() => route.path)
const wsConnected = computed(() => downloadStore.connected)

const pageTitle = computed(() => {
  switch (route.path) {
    case '/': return t('buttons.download')
    case '/jobs': return t('web.jobs')
    case '/history': return t('history.title')
    case '/settings': return t('settings.title')
    case '/tools': return t('buttons.custom_options')
    case '/updater': return t('tabs.updater')
    case '/about': return t('about.title')
    default: return 'YTSage'
  }
})

const activeCount = computed(() =>
  downloadStore.jobs.filter((j) => j.status === 'running' || j.status === 'paused').length
)

async function switchLang(v) {
  await loadLocale(v)
  try { await settingsStore.save({ language: v }) } catch {}
}

async function handleCommand(cmd) {
  if (cmd === 'logout') {
    try {
      await ElMessageBox.confirm('Logout?', 'Confirm', { type: 'warning' })
      authStore.logout()
      downloadStore.disconnectWebSocket()
      router.replace('/login')
    } catch {}
  }
}

onMounted(() => {
  downloadStore.connectWebSocket()
  settingsStore.fetch()
})

onBeforeUnmount(() => {
  downloadStore.disconnectWebSocket()
})
</script>

<style scoped>
.layout { height: 100vh; }
.aside {
  background-color: var(--yts-panel);
  border-right: 1px solid var(--yts-border);
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  border-bottom: 1px solid var(--yts-border);
}
.side-menu {
  flex: 1;
  border-right: none;
  background: transparent;
}
:deep(.el-menu) { background: transparent; }
:deep(.el-menu-item) { color: var(--yts-text-dim); }
:deep(.el-menu-item.is-active) { color: #ff6b6b; background: rgba(201, 0, 0, 0.12); }
:deep(.el-menu-item:hover) { background: rgba(201, 0, 0, 0.08); color: #fff; }
.version-info { padding: 14px 20px; border-top: 1px solid var(--yts-border); }
.job-badge { margin-left: 8px; }
.header {
  background: var(--yts-panel-2);
  border-bottom: 1px solid var(--yts-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.header h3 { margin: 0; color: var(--yts-text); font-size: 16px; }
.header-right { display: flex; align-items: center; }
.main { background: var(--yts-bg); padding: 20px; overflow-y: auto; }
</style>
