import { useState } from 'react'
import type { RefObject } from 'react'
import { Headphones, Pause, Play, Volume2, VolumeX, X } from 'lucide-react'
import { timeLabel } from './api'

export default function AudioPlayer({ audioRef, src, title, duration, position, hidden, onTimeUpdate, onSeeking, onManualSeek, onClose, onError }: {
  audioRef: RefObject<HTMLAudioElement | null>; src: string; title: string; duration: number; position: number; hidden: boolean
  onTimeUpdate: () => void; onSeeking: () => void; onManualSeek: (seconds: number) => void; onClose: () => void; onError: (message: string) => void
}) {
  const [playing, setPlaying] = useState(false)
  const [volume, setVolume] = useState(1)
  const [muted, setMuted] = useState(false)
  const [rate, setRate] = useState(1)
  const [mediaDuration, setMediaDuration] = useState(0)
  const length = mediaDuration || duration
  const current = Math.max(0, Math.min(position / 1000, length))
  const silent = muted || volume === 0

  async function togglePlay() {
    const media = audioRef.current
    if (!media) return
    if (!media.paused) { media.pause(); return }
    try { await media.play() } catch { onError('播放失败，请检查媒体文件后重试') }
  }
  function seek(seconds: number) {
    if (!audioRef.current) return
    try {
      // Clear the citation's stop point before the browser dispatches seeking.
      onManualSeek(seconds)
      audioRef.current.currentTime = seconds
    } catch { onError('暂时无法定位音频，请等待音频加载后重试') }
  }
  function syncVolume() {
    if (!audioRef.current) return
    setVolume(audioRef.current.volume); setMuted(audioRef.current.muted)
  }
  function toggleMute() {
    const media = audioRef.current
    if (!media) return
    if (silent && media.volume === 0) media.volume = 1
    media.muted = !silent
    syncVolume()
  }
  function updateDuration() {
    const value = audioRef.current?.duration
    setMediaDuration(value && Number.isFinite(value) && value > 0 ? value : 0)
  }

  return <footer id="classecho-player" className="player" aria-label="录音播放器" hidden={hidden}>
    <div className="player-title"><span><Headphones size={24} /></span><div><strong>{title}</strong><small>原始录音</small></div></div>
    <audio ref={audioRef} preload="metadata" src={src} onTimeUpdate={onTimeUpdate} onSeeking={onSeeking} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onLoadedMetadata={updateDuration} onDurationChange={updateDuration} onVolumeChange={syncVolume} onRateChange={() => setRate(audioRef.current?.playbackRate ?? 1)} />
    <button className="button player-toggle" aria-label={playing ? '暂停录音' : '播放录音'} onClick={() => void togglePlay()}>{playing ? <Pause size={24} /> : <Play size={24} />}</button>
    <div className="player-timeline"><p>{timeLabel(current * 1000)} / {timeLabel(length * 1000)}</p><input className="player-range" type="range" aria-label="播放进度" aria-valuetext={`${timeLabel(current * 1000)}，共 ${timeLabel(length * 1000)}`} min="0" max={length || 1} step="0.1" value={current} disabled={!length} onChange={event => seek(Number(event.target.value))} /></div>
    <button className="icon-button" aria-label={silent ? '取消静音' : '静音'} aria-pressed={silent} onClick={toggleMute}>{silent ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
    <input className="player-range player-volume" type="range" aria-label="音量" aria-valuetext={`${Math.round((silent ? 0 : volume) * 100)}%`} min="0" max="1" step="0.1" value={silent ? 0 : volume} onChange={event => { if (audioRef.current) { audioRef.current.volume = Number(event.target.value); audioRef.current.muted = false; syncVolume() } }} />
    <label className="speed-select"><span>倍速</span><select aria-label="播放速度" value={rate} onChange={event => { if (audioRef.current) { audioRef.current.playbackRate = Number(event.target.value); setRate(audioRef.current.playbackRate) } }}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label>
    <button className="icon-button" aria-label="关闭播放器" onClick={onClose}><X size={16} /></button>
  </footer>
}
