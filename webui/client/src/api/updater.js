/** Updater API */
import api from './http'

export function updaterState() {
  return api.get('/updater/state').then((r) => r.data)
}
export function checkYtdlp() {
  return api.post('/updater/ytdlp/check').then((r) => r.data)
}
export function updateYtdlp() {
  return api.post('/updater/ytdlp/update', null, { timeout: 300000 }).then((r) => r.data)
}
export function setYtdlpChannel(channel) {
  return api.post('/updater/ytdlp/channel', { channel }, { timeout: 200000 }).then((r) => r.data)
}
export function setYtdlpAuto(enabled, frequency) {
  return api.post('/updater/ytdlp/auto', { enabled, frequency }).then((r) => r.data)
}
export function checkFfmpeg() {
  return api.post('/updater/ffmpeg/check').then((r) => r.data)
}
export function installFfmpeg() {
  return api.post('/updater/ffmpeg/install', null, { timeout: 600000 }).then((r) => r.data)
}
export function checkDeno() {
  return api.post('/updater/deno/check').then((r) => r.data)
}
export function updateDeno() {
  return api.post('/updater/deno/update', null, { timeout: 600000 }).then((r) => r.data)
}
export function checkApp() {
  return api.post('/updater/app/check').then((r) => r.data)
}
