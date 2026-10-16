import { useEffect, useRef, useState } from 'react'
import { Download, Mic, Pause, Play, Square } from 'lucide-react'
import Dialog from './Dialog'
import { timeLabel } from './api'
import { microphoneError, recordingFile, recordingFormat } from './microphone'
import { LiveTranscription } from './liveTranscription'
import type { Segment } from './types'

type Phase = 'idle' | 'requesting' | 'recording' | 'paused' | 'review' | 'saving'

export default function MicrophoneRecorder({ courseName, liveReady = false, onClose, onSave }: {
  courseName: string; liveReady?: boolean; onClose: () => void; onSave: (file: File) => Promise<void>
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [title, setTitle] = useState(() => `课堂录音 ${new Date().toLocaleString('zh-CN', { hour12: false })}`)
  const [elapsed, setElapsed] = useState(0)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [liveEnabled, setLiveEnabled] = useState(true)
  const [liveStatus, setLiveStatus] = useState('')
  const [liveSegments, setLiveSegments] = useState<Segment[]>([])
  const live = useRef<LiveTranscription | null>(null)
  const mounted = useRef(true)
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const chunks = useRef<Blob[]>([])
  const bytes = useRef(0)
  const clock = useRef({ total: 0, since: 0 })
  const starting = useRef(false)

  function duration() { return clock.current.total + (clock.current.since ? performance.now() - clock.current.since : 0) }
  function stop() {
    clock.current.total = duration(); clock.current.since = 0
    setElapsed(clock.current.total)
    live.current?.dispose()
    if (recorder.current && recorder.current.state !== 'inactive') recorder.current.stop()
    stream.current?.getTracks().forEach(track => track.stop())
  }
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      live.current?.dispose()
      if (recorder.current && recorder.current.state !== 'inactive') recorder.current.stop()
      stream.current?.getTracks().forEach(track => track.stop())
    }
  }, [])
  useEffect(() => {
    if (!blob) return
    const next = URL.createObjectURL(blob); setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [blob])
  useEffect(() => {
    if (phase !== 'recording') return
    const timer = window.setInterval(() => {
      const value = duration(); setElapsed(value)
      if (value >= 90 * 60 * 1000) { setError('已达到 90 分钟，录音已结束，请保存。'); stop() }
    }, 500)
    return () => window.clearInterval(timer)
  }, [phase])
  useEffect(() => {
    if (phase === 'idle') return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [phase])

  async function start() {
    if (starting.current) return
    starting.current = true; setError(''); setPhase('requesting')
    let input: MediaStream | null = null
    try {
      const mimeType = recordingFormat()
      input = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true }, video: false })
      if (!mounted.current) { input.getTracks().forEach(track => track.stop()); return }
      stream.current = input
      if (liveEnabled && liveReady) {
        const preview = new LiveTranscription(
          segments => { if (mounted.current) setLiveSegments(previous => [...previous, ...segments].slice(-30)) },
          message => { if (mounted.current) setLiveStatus(message) },
        )
        live.current = preview
        try { await preview.start(input) }
        catch { preview.dispose(); setLiveStatus('实时采音不可用；仍可录音并在结束后转录。') }
        if (!mounted.current) { preview.dispose(); input.getTracks().forEach(track => track.stop()); return }
      }
      const media = new MediaRecorder(input, { mimeType })
      recorder.current = media; chunks.current = []; bytes.current = 0
      media.ondataavailable = event => {
        if (!mounted.current || !event.data.size) return
        chunks.current.push(event.data); bytes.current += event.data.size
        if (bytes.current >= 490 * 1024 ** 2 && media.state !== 'inactive') { setError('录音接近大小上限，已结束，请保存。'); stop() }
      }
      media.onstop = () => {
        if (!mounted.current) return
        const result = new Blob(chunks.current, { type: media.mimeType || mimeType })
        if (result.size) { setBlob(result); setPhase('review') }
        else { setError('没有录到音频，请检查输入设备后重试。'); setPhase('idle') }
      }
      media.onerror = () => { if (mounted.current) { setError('录音设备发生错误，已结束录音；可保存已有内容。'); stop() } }
      input.getAudioTracks().forEach(track => { track.onended = () => { if (mounted.current && media.state !== 'inactive') { setError('麦克风已断开，录音已结束，请保存已有内容。'); stop() } } })
      media.start(1000)
      live.current?.pause(false)
      clock.current = { total: 0, since: performance.now() }; setElapsed(0); setPhase('recording')
    } catch (failure) {
      input?.getTracks().forEach(track => track.stop())
      live.current?.dispose()
      if (mounted.current) { setError(microphoneError(failure)); setPhase('idle') }
    } finally { starting.current = false }
  }
  function togglePause() {
    const media = recorder.current
    if (!media) return
    if (media.state === 'recording') { clock.current.total = duration(); clock.current.since = 0; media.pause(); live.current?.pause(true); setElapsed(clock.current.total); setPhase('paused') }
    else if (media.state === 'paused') { media.resume(); live.current?.pause(false); clock.current.since = performance.now(); setPhase('recording') }
  }
  function close() {
    if (phase === 'saving') return
    if (phase !== 'idle' && !window.confirm('录音尚未保存，确定关闭并放弃本次录音吗？')) return
    onClose()
  }
  async function save() {
    if (!blob) return
    setPhase('saving'); setError('')
    try { await onSave(recordingFile(blob, title)) }
    catch (failure) { if (mounted.current) { setError(microphoneError(failure)); setPhase('review') } }
  }

  return <Dialog title="麦克风录音" closeLabel="关闭录音" onClose={close} className="recording-modal">
    <div className="recording-context">保存到「{courseName}」</div>
    <label className="recording-title">录音名称<input aria-label="录音名称" value={title} maxLength={120} disabled={phase === 'saving'} onChange={event => setTitle(event.target.value)} /></label>
    <div className="recording-status" role="status"><Mic size={18} /><strong>{timeLabel(elapsed)}</strong><span>{({ idle: '准备录音', requesting: '等待麦克风权限', recording: '正在录音', paused: '已暂停', review: '录音已结束', saving: '保存中' })[phase]}</span></div>
    <p className="muted recording-help">请保持页面打开。只录制麦克风输入，最长 90 分钟；暂停期间不计入录音。</p>
    <label className="recording-option"><input type="checkbox" checked={liveEnabled} disabled={phase !== 'idle' || !liveReady} onChange={event => setLiveEnabled(event.target.checked)} />本地实时转录（约每 10 秒更新）</label>
    {!liveReady && <p className="muted recording-help">Whisper small 尚未就绪，实时预览暂不可用；保存录音后可下载模型并转录。</p>}
    <div className="recording-actions">
      {phase === 'idle' && <button className="button primary" onClick={() => void start()}><Mic size={15} />开始录音</button>}
      {(phase === 'recording' || phase === 'paused') && <><button className="button" onClick={togglePause}>{phase === 'paused' ? <Play size={15} /> : <Pause size={15} />}{phase === 'paused' ? '继续录音' : '暂停录音'}</button><button className="button" onClick={stop}><Square size={14} />结束录音</button></>}
    </div>
    {liveStatus && <div className="live-preview"><h3>实时转录预览</h3><p className="muted" role="status">{phase === 'review' || phase === 'saving' ? '预览已停止，保存后可用完整录音校准。' : liveStatus}</p><div className="live-preview-lines" aria-label="实时识别文字">{liveSegments.map(segment => <p key={segment.id}><time>{timeLabel(segment.start_ms)}</time><span>{segment.text}</span></p>)}</div></div>}
    {blob && <div className="recording-review"><audio controls src={url} aria-label="本次录音预览" /><div className="recording-actions"><button className="button primary" disabled={phase === 'saving' || !title.trim()} onClick={() => void save()}>{phase === 'saving' ? '保存中…' : '保存录音'}</button><a className="button" href={url} download={recordingFile(blob, title).name}><Download size={14} />下载录音</a></div></div>}
    {error && <p className="recording-error" role="alert">{error}</p>}
  </Dialog>
}
