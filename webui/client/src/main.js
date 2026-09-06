import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import i18n, { loadLocale } from './i18n'
import './styles/theme.css'

// Force dark mode globally (official app is dark-only)
document.documentElement.classList.add('dark')

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.use(i18n)

// Preload saved language before mount
loadLocale(localStorage.getItem('ytsage_lang') || 'en').finally(() => {
  app.mount('#app')
})
