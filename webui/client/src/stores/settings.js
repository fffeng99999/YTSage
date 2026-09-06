/**
 * Settings store: caches /api/settings, exposes generic_mode & language,
 * applies language to i18n.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSettings, updateSettings } from '@/api/settings'
import { loadLocale } from '@/i18n'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref(null)
  const loaded = ref(false)

  const genericMode = computed(() => settings.value?.generic_mode !== false)
  const downloadPath = computed(() => settings.value?.download_path || '')
  const language = computed(() => settings.value?.language || 'en')
  const playSound = computed(() => settings.value?.play_notification_sound !== false)

  async function fetch(force = false) {
    if (loaded.value && !force) return settings.value
    try {
      settings.value = await getSettings()
      loaded.value = true
      localStorage.setItem('ytsage_settings_cache', JSON.stringify(settings.value))
      await loadLocale(language.value)
    } catch (e) {
      console.error('settings fetch failed:', e)
    }
    return settings.value
  }

  async function save(data) {
    settings.value = await updateSettings(data)
    if (data.language) await loadLocale(data.language)
    return settings.value
  }

  return { settings, loaded, genericMode, downloadPath, language, playSound, fetch, save }
})
