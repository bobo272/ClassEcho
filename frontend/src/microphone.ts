export function recordingFormat() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') throw new Error('当前浏览器不支持麦克风录音，请使用最新版 Chrome 或 Safari，并通过 localhost 打开。')
  const mime = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(type => MediaRecorder.isTypeSupported(type))
  if (!mime) throw new Error('浏览器没有可用的录音格式，请尝试 Chrome 或 Safari。')
  return mime
}

export function microphoneError(error: unknown) {
  const name = error && typeof error === 'object' && 'name' in error ? String(error.name) : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') return '麦克风权限未获允许，请在浏览器或系统设置中允许后重试。'
  if (name === 'NotFoundError') return '没有找到麦克风，请连接输入设备后重试。'
  if (name === 'NotReadableError') return '麦克风无法使用，可能被其他程序占用。'
  return error instanceof Error ? error.message : '无法启动录音，请检查麦克风。'
}

export function recordingFile(blob: Blob, title: string) {
  const name = title.trim().replace(/[\\/\u0000-\u001f]/g, '_').slice(0, 120) || '课堂录音'
  return new File([blob], `${name}.${blob.type.includes('mp4') ? 'm4a' : 'webm'}`, { type: blob.type })
}
