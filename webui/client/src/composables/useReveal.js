/**
 * Reveal / open-folder helpers (official open_download_folder).
 *
 * Local vs remote adaptation (module 6.2):
 * - localhost: reveal in the server's file explorer (desktop parity).
 * - remote (LAN / NAS / VPS): opening the *server-side* explorer is useless,
 *   so reveal transparently becomes a direct browser download instead.
 */
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { revealPath, openFolder } from '@/api/system'
import { useEnv } from './useEnv'

export function useReveal() {
  const { t } = useI18n()
  const { local, fileDownloadUrl } = useEnv()

  /** True when the "reveal" button should open the server-side explorer. */
  const canReveal = local

  function directDownload(filePath) {
    if (!filePath) return
    const a = document.createElement('a')
    a.href = fileDownloadUrl(filePath)
    a.download = ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  async function reveal(filePath) {
    if (!filePath) return
    if (!local) {
      directDownload(filePath)
      return
    }
    try {
      await revealPath(filePath)
    } catch (e) {
      ElMessage.warning(t('main_ui.open_folder_error', { error: e?.response?.data?.detail || e.message }))
    }
  }

  async function openDir(dirPath) {
    if (!dirPath) return
    if (!local) {
      ElMessage.info(t('web.env.remote_no_explorer'))
      return
    }
    try {
      await openFolder(dirPath)
    } catch (e) {
      ElMessage.warning(t('main_ui.open_folder_error', { error: e?.response?.data?.detail || e.message }))
    }
  }

  return { reveal, openDir, directDownload, canReveal, local }
}
