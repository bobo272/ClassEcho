import { useState } from 'react'
import { Check, Headphones, Pencil, RotateCcw, X } from 'lucide-react'
import { timeLabel } from './api'
import type { Note, Segment } from './types'

export default function NoteContent({ note, segments, drafts, busy, onEdit, onSave, onDiscard, onSeek }: {
  note: Note; segments: Segment[]; drafts: Record<string, string>; busy: boolean
  onEdit: (key: string, text: string) => void; onSave: () => void; onDiscard: () => void; onSeek: (segment: Segment) => void
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const hasDrafts = Object.keys(drafts).length > 0
  const invalid = Object.values(drafts).some(text => !text.trim() || text.length > 5000)
  return <>
    {hasDrafts && <div className="note-edit-bar"><span>正文有未保存的修改</span><button className="button small" disabled={busy || invalid} onClick={onSave}><Check size={13} />保存正文</button><button aria-label="放弃正文修改" disabled={busy} onClick={onDiscard}><X size={14} /></button></div>}
    <div className="note-content">{note.content.sections.map((section, sectionIndex) => <section key={sectionIndex}>
      <h3><span>{(sectionIndex + 1).toString().padStart(2, '0')}</span>{section.heading}</h3>
      {section.items.map((item, itemIndex) => {
        const key = `${sectionIndex}.${itemIndex}`
        const text = drafts[key] ?? note.text_edits?.[key] ?? item.text
        const changed = text !== item.text
        return <div className="note-item" key={key}>
          <div className="note-item-actions">{changed && <span>用户修订</span>}<button aria-label={`修改笔记 ${sectionIndex + 1}.${itemIndex + 1}`} onClick={() => setEditing(editing === key ? null : key)}><Pencil size={12} /></button>{changed && <button aria-label={`恢复原始笔记 ${sectionIndex + 1}.${itemIndex + 1}`} disabled={busy} onClick={() => onEdit(key, item.text)}><RotateCcw size={12} /></button>}</div>
          {editing === key ? <textarea aria-label={`笔记正文 ${sectionIndex + 1}.${itemIndex + 1}`} value={text} maxLength={5000} disabled={busy} onChange={event => onEdit(key, event.target.value)} /> : <p onDoubleClick={() => setEditing(key)}>{text}</p>}
          {changed && <details><summary>查看原始笔记</summary><p>{item.text}</p></details>}
          <div className="citations">{item.source_segment_ids.map(id => {
            const segment = segments.find(s => s.id === id)
            return <button disabled={!segment} key={id} onClick={() => { if (segment) onSeek(segment) }}><Headphones size={11} />{segment ? timeLabel(segment.start_ms) : '加载引用'}<span>↗</span></button>
          })}</div>
        </div>
      })}
    </section>)}</div>
  </>
}
