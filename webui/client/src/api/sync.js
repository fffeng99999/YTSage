/**
 * YT Sync center API (dysync.net-inspired, targeted at YouTube)
 */
import api from './http'

// ---- profiles ----------------------------------------------------------

export function listProfiles() {
  return api.get('/sync/profiles').then((r) => r.data)
}

export function getProfile(id) {
  return api.get(`/sync/profiles/${id}`).then((r) => r.data)
}

export function createProfile(data) {
  return api.post('/sync/profiles', data).then((r) => r.data)
}

export function updateProfile(id, data) {
  return api.put(`/sync/profiles/${id}`, data).then((r) => r.data)
}

export function deleteProfile(id) {
  return api.delete(`/sync/profiles/${id}`).then((r) => r.data)
}

// ---- targets -----------------------------------------------------------

export function createTarget(profileId, data) {
  return api.post(`/sync/profiles/${profileId}/targets`, data).then((r) => r.data)
}

export function updateTarget(id, data) {
  return api.put(`/sync/targets/${id}`, data).then((r) => r.data)
}

export function deleteTarget(id) {
  return api.delete(`/sync/targets/${id}`).then((r) => r.data)
}

// ---- run / runs --------------------------------------------------------

export function runSync(profileId, targetIds) {
  return api.post('/sync/run', { profile_id: profileId, target_ids: targetIds }).then((r) => r.data)
}

export function latestRuns() {
  return api.get('/sync/runs/latest').then((r) => r.data)
}

// ---- records -----------------------------------------------------------

export function listRecords(params) {
  return api.get('/sync/records', { params }).then((r) => r.data)
}

export function deleteRecord(id) {
  return api.delete(`/sync/records/${id}`).then((r) => r.data)
}

export function deleteRecords(ids) {
  return api.delete('/sync/records', { params: { ids } }).then((r) => r.data)
}

export function resyncRecords(ids) {
  return api.post('/sync/records/resync', { record_ids: ids }).then((r) => r.data)
}

// ---- excludes ----------------------------------------------------------

export function listExcludes() {
  return api.get('/sync/excludes').then((r) => r.data)
}

export function addExclude(videoId, reason) {
  return api.post('/sync/excludes', { video_id: videoId, reason }).then((r) => r.data)
}

export function removeExclude(videoId) {
  return api.delete(`/sync/excludes/${videoId}`).then((r) => r.data)
}

// ---- schedules ---------------------------------------------------------

export function listSchedules() {
  return api.get('/sync/schedules').then((r) => r.data)
}

export function createSchedule(data) {
  return api.post('/sync/schedules', data).then((r) => r.data)
}

export function updateSchedule(id, data) {
  return api.put(`/sync/schedules/${id}`, data).then((r) => r.data)
}

export function deleteSchedule(id) {
  return api.delete(`/sync/schedules/${id}`).then((r) => r.data)
}

// ---- settings / logs ---------------------------------------------------

export function getSyncSettings() {
  return api.get('/sync/settings').then((r) => r.data)
}

export function setSyncSettings(data) {
  return api.post('/sync/settings', data).then((r) => r.data)
}

export function clearSyncLogs() {
  return api.post('/sync/logs/clear').then((r) => r.data)
}

export function pruneSyncLogs() {
  return api.post('/sync/logs/prune').then((r) => r.data)
}

// ---- export / import / status -----------------------------------------

export function exportSync() {
  return api.get('/sync/export').then((r) => r.data)
}

export function importSync(data) {
  return api.post('/sync/import', data).then((r) => r.data)
}

export function syncStatus() {
  return api.get('/sync/status').then((r) => r.data)
}

// ---- statistics --------------------------------------------------------

export function getStatistics() {
  return api.get('/sync/statistics').then((r) => r.data)
}

export function getTrendStats(days = 7) {
  return api.get('/sync/statistics/trend', { params: { days } }).then((r) => r.data)
}

export function getAuthorStats(page = 1, limit = 30) {
  return api.get('/sync/statistics/authors', { params: { page, limit } }).then((r) => r.data)
}

export function deleteAuthorRecords(channel) {
  return api.delete(`/sync/statistics/authors/${encodeURIComponent(channel)}`).then((r) => r.data)
}

// ---- nfo generation ----------------------------------------------------

export function generateNFO(videoId) {
  return api.post(`/sync/nfo/generate/${videoId}`).then((r) => r.data)
}

export function generateNFOBatch(videoIds) {
  return api.post('/sync/nfo/generate-batch', { video_ids: videoIds }).then((r) => r.data)
}

// ---- records enhancements ----------------------------------------------

export function batchDeleteRecords(ids) {
  return api.post('/sync/records/batch-delete', { ids }).then((r) => r.data)
}

export function restoreRecord(videoId) {
  return api.post(`/sync/records/${videoId}/restore`).then((r) => r.data)
}

export function getDeletedRecords(page = 1, limit = 20) {
  return api.get('/sync/records/deleted', { params: { page, limit } }).then((r) => r.data)
}

export function batchRedownloadRecords(ids) {
  return api.post('/sync/records/batch-redownload', { ids }).then((r) => r.data)
}

export function permanentDeleteRecords(ids, deleteFiles = false, alsoExclude = true) {
  return api.post('/sync/records/permanent-delete', { ids, delete_files: deleteFiles, also_exclude: alsoExclude }).then((r) => r.data)
}

export function listRecordChannels() {
  return api.get('/sync/records/channels').then((r) => r.data)
}

export function scanMissingRecords() {
  return api.post('/sync/records/scan-missing').then((r) => r.data)
}

export function removeMissingRecords(deleteFiles = false) {
  return api.post('/sync/records/remove-missing', { delete_files: deleteFiles }).then((r) => r.data)
}

export function createShareLink(videoId) {
  return api.post(`/sync/records/${videoId}/share`).then((r) => r.data)
}

// ---- subscriptions -----------------------------------------------------

export function getSubscriptions(profileId) {
  return api.get(`/sync/subscriptions/${profileId}`).then((r) => r.data)
}

export function pullSubscriptions(profileId) {
  return api.post('/sync/subscriptions/pull', null, { params: { profile_id: profileId } }).then((r) => r.data)
}

export function addSubscription(profileId, channelUrl, channelName) {
  return api.post('/sync/subscriptions/add', { 
    profile_id: profileId, 
    channel_url: channelUrl, 
    channel_name: channelName 
  }).then((r) => r.data)
}

export function saveSubscriptions(profileId, channels, syncMode = 'off') {
  return api.post('/sync/subscriptions/save', {
    profile_id: profileId, channels, sync_mode: syncMode,
  }).then((r) => r.data)
}

export function updateTargetSyncMode(targetId, syncMode) {
  return api.put(`/sync/targets/${targetId}/sync-mode`, { sync_mode: syncMode }).then((r) => r.data)
}

export function updateTargetSavePath(targetId, savePath) {
  return api.put(`/sync/targets/${targetId}/save-path`, { save_path: savePath }).then((r) => r.data)
}

export function getSubscriptionStats(profileId) {
  return api.get(`/sync/subscriptions/${profileId}/stats`).then((r) => r.data)
}

// ---- cookies -----------------------------------------------------------

export function getCookieStatus() {
  return api.get('/sync/cookies/status').then((r) => r.data)
}

export function checkCookie(profileId) {
  return api.post(`/sync/cookies/check/${profileId}`).then((r) => r.data)
}

// ---- streaming ---------------------------------------------------------

export function getVideoStreamUrl(videoId) {
  // <video> tags cannot send Authorization headers, so the signed token
  // travels as a query parameter (server accepts it for /api/sync/stream).
  const token = localStorage.getItem('ytsage_token') || ''
  return `/api/sync/stream/${videoId}?token=${encodeURIComponent(token)}`
}