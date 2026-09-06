<template>
  <div class="about-page">
    <div class="yts-card">
      <div class="brand-row">
        <el-icon :size="42" color="#c90000"><VideoCamera /></el-icon>
        <div>
          <h2>YTSage</h2>
          <p class="help">{{ t('about.version') }}: {{ health.app_version || '-' }}</p>
          <p class="help">{{ t('about.description') }}</p>
        </div>
      </div>
      <div class="links">
        <a href="https://github.com/oop7/YTSage" target="_blank">{{ t('about.github') }}</a>
        <a href="https://github.com/sponsors/oop7" target="_blank">{{ t('about.sponsor') }}</a>
      </div>
    </div>

    <div class="yts-card">
      <div class="yts-card-title">{{ t('about.system_info') }}</div>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="yt-dlp">
          <el-tag size="small" :type="sys.ytdlp?.installed ? 'success' : 'danger'">
            {{ sys.ytdlp?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.ytdlp?.version }}</span>
          <code class="path">{{ sys.ytdlp?.path }}</code>
        </el-descriptions-item>
        <el-descriptions-item label="FFmpeg">
          <el-tag size="small" :type="sys.ffmpeg?.installed ? 'success' : 'danger'">
            {{ sys.ffmpeg?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.ffmpeg?.version }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="Deno">
          <el-tag size="small" :type="sys.deno?.installed ? 'success' : 'danger'">
            {{ sys.deno?.installed ? t('about.detected') : t('about.missing') }}
          </el-tag>
          <span class="ver">{{ sys.deno?.version }}</span>
          <el-tag size="small" :type="sys.deno?.integrated_with_ytdlp ? 'success' : 'info'" style="margin-left: 8px">
            {{ sys.deno?.integrated_with_ytdlp ? 'yt-dlp ✓' : 'yt-dlp ✗' }}
          </el-tag>
          <code class="path">{{ sys.deno?.path }}</code>
        </el-descriptions-item>
      </el-descriptions>
      <div class="row">
        <el-button size="small" @click="load" :loading="loading">
          <el-icon><Refresh /></el-icon> {{ t('about.refresh') }}
        </el-button>
        <el-button size="small" @click="openLogs" :title="t('about.logs_tooltip')">📂 Logs</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { Refresh, VideoCamera } from '@element-plus/icons-vue'
import { systemStatus, openLogs as apiOpenLogs } from '@/api/system'
import { getHealth } from '@/api/settings'
import { errText } from '@/api/http'

const { t } = useI18n()
const sys = ref({})
const health = ref({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    sys.value = await systemStatus()
    health.value = await getHealth()
  } catch (e) {
    ElMessage.error(t('about.refresh_failed') + ': ' + errText(e))
  } finally {
    loading.value = false
  }
}

async function openLogs() {
  try { await apiOpenLogs() } catch (e) { ElMessage.error(errText(e)) }
}

onMounted(load)
</script>

<style scoped>
.brand-row { display: flex; gap: 16px; align-items: center; }
.brand-row h2 { margin: 0; }
.help { color: var(--yts-text-dim); font-size: 13px; margin: 4px 0; }
.links { margin-top: 12px; display: flex; gap: 16px; }
.links a { color: var(--yts-red); font-size: 13px; }
.ver { margin-left: 12px; }
.path { margin-left: 12px; font-size: 11px; color: var(--yts-text-dim); word-break: break-all; }
.row { margin-top: 12px; display: flex; gap: 10px; }
</style>
