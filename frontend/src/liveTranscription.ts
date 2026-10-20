import workletUrl from './capture.worklet.ts?worker&url'
import { api } from './api'
import { PCM_RATE, wavBlob } from './pcm'
import type { Segment } from './types'

type Preview = { id: string; state: string; segments: Segment[]; error: string | null }
export class LiveTranscription {
  private context: AudioContext | null = null
  private source: MediaStreamAudioSourceNode | null = null
  private node: AudioWorkletNode | null = null
  private samples: number[] = []
  private total = 0
  private busy = false
  private disposed = false
  private abort = new AbortController()
  constructor(private onText: (segments: Segment[]) => void, private onStatus: (value: string) => void) {}

  async start(stream: MediaStream) {
    this.context = new AudioContext()
    if (!this.context.audioWorklet) throw new Error('浏览器不支持实时采音，录音结束后仍可转录。')
    await this.context.audioWorklet.addModule(workletUrl)
    if (this.disposed) { await this.context.close(); return }
    this.source = this.context.createMediaStreamSource(stream)
    this.node = new AudioWorkletNode(this.context, 'classecho-microphone', { channelCount: 1, channelCountMode: 'explicit' })
    this.node.port.onmessage = event => this.accept(event.data as Int16Array)
    this.node.onprocessorerror = () => this.onStatus('实时采音中断，完整录音仍在继续，结束后可校准。')
    this.source.connect(this.node); this.node.connect(this.context.destination)
    await this.context.resume()
    this.onStatus('等待语音：约每 10 秒更新，文字为临时预览。')
  }
  pause(paused: boolean) { this.node?.port.postMessage({ paused }) }
  accept(samples: Int16Array) {
    if (this.disposed) return
    this.total += samples.length
    for (const value of samples) this.samples.push(value)
    // Keep only the latest window if inference is slower than recording; the full
    // MediaRecorder stream is independent and is never discarded here.
    const maximum = 10 * PCM_RATE
    if (this.samples.length > maximum) this.samples.splice(0, this.samples.length - maximum)
    if (!this.busy && this.samples.length >= maximum) void this.preview()
  }
  private async preview() {
    this.busy = true
    const samples = new Int16Array(this.samples), offset = Math.round((this.total - samples.length) / PCM_RATE * 1000)
    this.samples = []
    try {
      this.onStatus('本地识别中，录音仍在继续…')
      const body = new FormData(); body.append('file', wavBlob(samples), 'preview.wav'); body.append('model', 'small'); body.append('offset_ms', String(offset))
      let result = await api<Preview>('/live-transcriptions', { method: 'POST', body, signal: this.abort.signal })
      while (!this.disposed && ['queued', 'running'].includes(result.state)) {
        await new Promise<void>(resolve => {
          const finish = () => { clearTimeout(timer); this.abort.signal.removeEventListener('abort', finish); resolve() }
          const timer = setTimeout(finish, 1000)
          this.abort.signal.addEventListener('abort', finish, { once: true })
          if (this.abort.signal.aborted) finish()
        })
        if (!this.disposed) result = await api<Preview>(`/live-transcriptions/${result.id}`, { signal: this.abort.signal })
      }
      if (this.disposed) return
      if (result.state !== 'succeeded') throw new Error(result.error || '实时识别暂不可用')
      if (result.segments.length) this.onText(result.segments)
      this.onStatus(result.segments.length ? '已更新；结束录音后可用完整音频校准。' : '这段未识别到语音，继续等待…')
    } catch (error) {
      if (!this.disposed) this.onStatus(`${error instanceof Error ? error.message : '实时识别暂不可用'}。完整录音仍在继续。`)
    } finally {
      this.busy = false
      if (!this.disposed && this.samples.length >= 10 * PCM_RATE) void this.preview()
    }
  }
  dispose() {
    this.disposed = true; this.abort.abort(); this.samples = []
    this.source?.disconnect(); this.node?.disconnect()
    if (this.node) this.node.port.onmessage = null
    if (this.context && this.context.state !== 'closed') void this.context.close().catch(() => {})
  }
}
