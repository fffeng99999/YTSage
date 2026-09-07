/**
 * Clipboard read with a reliable fallback.
 *
 * navigator.clipboard is ONLY available in secure contexts (https or
 * localhost). The WebUI is often opened via http://<LAN-IP>:8765, where the
 * async clipboard API is undefined and the old code fell straight into the
 * "please enter a URL" warning. When the API is unavailable/denied, we show a
 * small dialog the user can paste into with Ctrl+V (keyboard paste always
 * works), then return that text.
 */
import { ElMessageBox } from 'element-plus'
import i18n from '@/i18n'

const { t } = i18n.global

export async function readClipboardText() {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      const text = await navigator.clipboard.readText()
      if (text && text.trim()) return text.trim()
    }
  } catch { /* permission denied or unavailable - fall through */ }

  // Fallback: modal input the user pastes into (Ctrl+V works everywhere)
  try {
    const { value } = await ElMessageBox.prompt(
      t('web.clipboard_manual_paste'),
      t('buttons.paste_url'),
      {
        inputValue: '',
        inputType: 'textarea',
        confirmButtonText: t('buttons.ok'),
        cancelButtonText: t('buttons.cancel'),
        inputPlaceholder: t('web.clipboard_manual_placeholder'),
      }
    )
    return (value || '').trim()
  } catch {
    return '' // cancelled
  }
}
