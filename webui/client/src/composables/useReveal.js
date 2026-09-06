/**
 * Reveal / open-folder helpers (official open_download_folder).
 */
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { revealPath, openFolder } from '@/api/system'

export function useReveal() {
  const { t } = useI18n()

  async function reveal(filePath) {
    if (!filePath) return
    try {
      await revealPath(filePath)
    } catch (e) {
      ElMessage.warning(t('main_ui.open_folder_error', { error: e?.response?.data?.detail || e.message }))
    }
  }

  async function openDir(dirPath) {
    if (!dirPath) return
    try {
      await openFolder(dirPath)
    } catch (e) {
      ElMessage.warning(t('main_ui.open_folder_error', { error: e?.response?.data?.detail || e.message }))
    }
  }

  return { reveal, openDir }
}
