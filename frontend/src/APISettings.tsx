import { useState } from 'react'
import { api } from './api'
import type { NotesAPIConfig } from './types'

export default function APISettings({ config, onSaved }: { config: NotesAPIConfig; onSaved: (config: NotesAPIConfig) => void }) {
  const [baseUrl, setBaseUrl] = useState(config.base_url)
  const [model, setModel] = useState(config.model)
  const [key, setKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  async function save(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError(''); setSaved(false)
    try {
      const result = await api<NotesAPIConfig>('/settings/notes-api', { method: 'PUT', body: JSON.stringify({ base_url: baseUrl, model, ...(key.trim() ? { api_key: key.trim() } : {}) }) })
      setKey(''); setBaseUrl(result.base_url); setModel(result.model); onSaved(result); setSaved(true)
    } catch (error) { setError(error instanceof Error ? error.message : '保存失败') } finally { setSaving(false) }
  }

  return <form className="setting-block api-settings" onSubmit={save} onChange={() => setSaved(false)}>
    <h3>AI 接口</h3>
    <p className="muted">使用你自己的模型服务或中转接口，需兼容 Chat Completions。</p>
    <label>API URL<input type="url" required maxLength={2000} placeholder="https://你的接口地址/v1" value={baseUrl} onChange={event => setBaseUrl(event.target.value)} /></label>
    <small>填写服务商提供的基础地址（含 /v1 等路径），也支持完整的 /chat/completions 地址。</small>
    <label>模型名称<input required maxLength={200} placeholder="填写接口支持的模型名称" value={model} onChange={event => setModel(event.target.value)} /></label>
    <label>API Key<input type="password" autoComplete="off" maxLength={8192} placeholder={config.key_configured && baseUrl === config.base_url ? '已保存，留空保留原密钥' : '填写此接口的密钥'} value={key} onChange={event => setKey(event.target.value)} /></label>
    <small>密钥保存在本机，不会读回页面。更换接口地址后请重新填写密钥。</small>
    <button className="button primary" disabled={saving}>{saving ? '保存中…' : '保存接口'}</button>
    {error && <p role="alert">{error}</p>}
    {saved && <p role="status">{config.configured ? '接口已保存，整理笔记时可选择 AI 接口。' : '地址和模型已保存，请补充此接口的密钥。'}</p>}
  </form>
}
