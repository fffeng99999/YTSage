/**
 * i18n setup: messages are fetched from the backend /api/i18n/{lang},
 * which serves the OFFICIAL ytsage/languages/{zh,en}.json files verbatim.
 * Frontend uses the same dotted keys as the desktop app (e.g.
 * t('main_ui.url_placeholder')), so upstream text changes sync for free.
 */
import { createI18n } from 'vue-i18n'
import axios from 'axios'

export const SUPPORTED_LANGS = ['en', 'zh']

const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem('ytsage_lang') || 'en',
  fallbackLocale: 'en',
  messages: {},
  // Official files use {name} named interpolation - compatible with vue-i18n
  missingWarn: false,
  fallbackWarn: false,
})

const loaded = new Set()

// Web-specific strings that don't exist in the official desktop language
// files (the desktop app has no Jobs page / security tab / etc.)
const WEB_EXTRA = {
  en: {
    web: {
      jobs: 'Download Jobs', security: 'Security', logout: 'Logout',
      confirm_logout: 'Are you sure you want to logout?',
      current_password: 'Current Password', new_password: 'New Password',
      confirm_password: 'Confirm Password', change_password: 'Change Password',
      password_changed: 'Password changed successfully',
      fill_all_fields: 'Please fill all fields',
      passwords_mismatch: 'Passwords do not match',
      password_too_short: 'Password too short (min 4 chars)',
      notification_sounds: 'Notification Sounds',
      recent_downloads: 'Recent Downloads',
      embed: 'Embed', chapters: 'Chapters', metadata: 'Metadata', thumbnail: 'Thumbnail',
      default_password_hint: 'Default password: ytsage',
      download_path_label: 'Download Path',
    },
  },
  zh: {
    web: {
      jobs: '下载任务', security: '安全', logout: '退出登录',
      confirm_logout: '确定要退出登录吗?',
      current_password: '当前密码', new_password: '新密码',
      confirm_password: '确认新密码', change_password: '修改密码',
      password_changed: '密码修改成功',
      fill_all_fields: '请填写所有字段',
      passwords_mismatch: '两次输入的密码不一致',
      password_too_short: '密码太短(至少 4 位)',
      notification_sounds: '通知声音',
      recent_downloads: '最近下载',
      embed: '嵌入选项', chapters: '章节', metadata: '元数据', thumbnail: '封面',
      default_password_hint: '默认密码: ytsage',
      download_path_label: '下载路径',
      login: '登录', login_failed_invalid: '密码错误',
    },
  },
}

export async function loadLocale(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en'
  if (loaded.has(lang)) {
    i18n.global.locale.value = lang
    localStorage.setItem('ytsage_lang', lang)
    return
  }
  try {
    const { data } = await axios.get(`/api/i18n/${lang}`, { timeout: 15000 })
    i18n.global.setLocaleMessage(lang, { ...data, ...(WEB_EXTRA[lang] || {}) })
    loaded.add(lang)
    i18n.global.locale.value = lang
    localStorage.setItem('ytsage_lang', lang)
  } catch (e) {
    console.error('loadLocale failed:', e)
    if (lang !== 'en') await loadLocale('en')
  }
}

export default i18n
