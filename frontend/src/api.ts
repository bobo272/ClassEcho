export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers } })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : response.status === 422 ? '提交内容不符合要求，请检查输入' : `请求失败（${response.status}）`)
  }
  return response.status === 204 ? undefined as T : response.json()
}

export function timeLabel(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000))
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}

export function noteIsStale(noteTranscript: string, activeTranscript: string | null) {
  return noteTranscript !== activeTranscript
}
