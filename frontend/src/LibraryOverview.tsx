import { ArrowUpRight, FileAudio, FolderOpen, LoaderCircle, Plus, Upload } from 'lucide-react'
import { timeLabel } from './api'
import type { Lecture } from './types'

export default function LibraryOverview({ courseName, lectures, busy, onOpen, onImport, onDemo, onDrop }: {
  courseName: string; lectures: Lecture[]; busy: boolean; onOpen: (id: string) => void
  onImport: () => void; onDemo: () => void; onDrop: (file: File | undefined) => void
}) {
  return <section className="library-overview">
    <header className="library-heading"><p>课程资料</p><h1>{courseName}</h1><div><span>{lectures.length} 份录音</span><button className="button primary" disabled={busy} onClick={onImport}><Plus size={15} />导入录音</button></div></header>
    {lectures.length > 0 ? <div className="library-table"><div className="library-table-heading"><span>名称</span><span>时长</span><span>状态</span></div>{lectures.map(lecture => <button className="library-entry" key={lecture.id} onClick={() => onOpen(lecture.id)}><span><FileAudio size={17} /><strong>{lecture.title}</strong></span><time>{timeLabel(lecture.duration * 1000)}</time><small>{lecture.is_demo ? '示例' : lecture.active_transcript_id ? '已转录' : '待转录'}</small></button>)}</div> : <div className="library-empty"><FolderOpen size={30} strokeWidth={1.3} /><h2>从一份课程录音开始</h2><p>导入后可转录、整理笔记和回听原文。</p></div>}
    <div className="import-dropzone" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); onDrop(event.dataTransfer.files[0]) }}><Upload size={19} /><div><strong>拖放音视频文件到这里</strong><small>MP3、M4A、WAV、MP4、WebM · 最大 500MB · 最长 90 分钟</small></div><button className="button" disabled={busy} onClick={onImport}>{busy ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />}选择文件</button></div>
    <button className="demo-link" disabled={busy} onClick={onDemo}>打开内置示例<ArrowUpRight size={14} /></button>
  </section>
}
