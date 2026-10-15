import { useState } from 'react'
import { Check, Pencil, Play, X } from 'lucide-react'
import type { Segment } from './types'
import { timeLabel } from './api'

export default function TranscriptPane({ segments, current, dirty, onSeek, onEdit, onSave, onDiscard, readOnly = false }: { segments: Segment[]; current: number; dirty: Record<string, string>; onSeek: (segment: Segment) => void; onEdit: (id: string, value: string) => void; onSave: () => void; onDiscard: () => void; readOnly?: boolean }) {
  const [editing, setEditing] = useState<string | null>(null)
  return <>
    <div className="pane-heading"><div><span className="eyebrow">TRANSCRIPT</span><h2>课堂原文 <small>{segments.length} 段</small></h2></div><Pencil size={16} /></div>
    {Object.keys(dirty).length > 0 && <div className="edit-bar"><span>{Object.keys(dirty).length} 处待保存</span><button onClick={onSave}><Check size={14} />保存为新版本</button><button aria-label="放弃转录修改" onClick={onDiscard}><X size={14} /></button></div>}
    <div className="segments">{segments.map(segment => <article key={segment.id} className={`segment ${current >= segment.start_ms && current < segment.end_ms ? 'active' : ''}`}>
      <div className="segment-meta"><button onClick={() => onSeek(segment)} aria-label={`回听 ${timeLabel(segment.start_ms)}`}><Play size={11} fill="currentColor" />{timeLabel(segment.start_ms)}</button>{!readOnly && <button aria-label={`修改片段 ${segment.id}`} onClick={() => setEditing(editing === segment.id ? null : segment.id)}><Pencil size={12} /></button>}</div>
      {!readOnly && editing === segment.id ? <textarea aria-label={`片段文字 ${segment.id}`} value={dirty[segment.id] ?? segment.text} onChange={event => onEdit(segment.id, event.target.value)} /> : <p onDoubleClick={() => { if (!readOnly) setEditing(segment.id) }}>{dirty[segment.id] ?? segment.text}</p>}
      {segment.raw_text !== segment.text && <details><summary>识别原文</summary><p>{segment.raw_text}</p></details>}
    </article>)}</div>
  </>
}
