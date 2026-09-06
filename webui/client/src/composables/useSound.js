/**
 * Notification sound (official play_notification_sound with notification.mp3).
 * Respects the play_notification_sound setting.
 */
import { useSettingsStore } from '@/stores/settings'

let audio = null

export function playNotification() {
  try {
    const settings = useSettingsStore()
    if (settings.playSound === false) return
    if (!audio) {
      audio = new Audio('/api/sound/notification')
      audio.volume = 0.6
    }
    audio.currentTime = 0
    audio.play().catch(() => {})
  } catch (e) {
    // browser autoplay policy - ignore
  }
}
