/**
 * A ref that survives route changes for the lifetime of the browser tab
 * (sessionStorage: kept until the tab/browser closes, or the value is
 * overwritten/cleared by the user). Used to keep pasted URLs when
 * navigating between pages.
 */
import { ref, watch } from 'vue'

export function useSessionRef(key, initial = '') {
  let start = initial
  try {
    const v = sessionStorage.getItem(key)
    if (v !== null) start = v
  } catch { /* private mode etc. */ }

  const r = ref(start)
  watch(r, (v) => {
    try {
      if (v) sessionStorage.setItem(key, v)
      else sessionStorage.removeItem(key)
    } catch { /* ignore quota / privacy errors */ }
  })
  return r
}
