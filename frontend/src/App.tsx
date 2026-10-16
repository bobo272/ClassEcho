import { useCallback, useEffect, useRef, useState } from 'react'
import { AudioLines, ArrowDownToLine, ArrowLeft, BookOpen, Check, ChevronDown, CircleHelp, Clock3, FileAudio, FileText, Headphones, LoaderCircle, Plus, RotateCcw, Settings2, ShieldCheck, Sparkles, Trash2, Upload, X } from 'lucide-react'
import { api, noteIsStale, timeLabel } from './api'
import type { Course, Detail, Job, Lecture, Note, Segment, Settings, Transcript } from './types'
import TranscriptPane from './TranscriptPane'
import APISettings from './APISettings'
import NoteContent from './NoteContent'
import { readWorkspace, saveWorkspace } from './workspace'

const stageNames: Record<string, string> = { queued: '等待处理', normalize: '规范化音频', download: '检查或下载模型（首次较慢）', transcribe: '本地转录中', draft: '整理笔记中', validate: '检查来源引用', complete: '已完成' }

export default function App() {
  const [savedWorkspace] = useState(readWorkspace)
  const restorePending = useRef(true)
  const loadedCourse = useRef('')
  const [courses, setCourses] = useState<Course[]>([])
  const [courseId, setCourseId] = useState('')
  const [lectures, setLectures] = useState<Lecture[]>([])
  const [lectureId, setLectureId] = useState('')
  const currentLectureId = useRef(lectureId)
  currentLectureId.current = lectureId
  const [detail, setDetail] = useState<Detail | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showCourse, setShowCourse] = useState(false)
  const [courseName, setCourseName] = useState('')
  const [model, setModel] = useState('small')
  const [provider, setProvider] = useState('extractive')
  const [consent, setConsent] = useState(false)
  const [dirty, setDirty] = useState<Record<string, string>>({})
  const dirtyVersion = useRef<string | null>(null)
  const [noteId, setNoteId] = useState('')
  const [userText, setUserText] = useState('')
  const [noteDirty, setNoteDirty] = useState(false)
  const [noteEdits, setNoteEdits] = useState<Record<string, string>>({})
  const bodyDirty = Object.keys(noteEdits).length > 0
  const noteVersion = useRef<{ id: string; edit_version: number } | null>(null)
  const [source, setSource] = useState<Transcript | null>(null)
  const [showNoteSource, setShowNoteSource] = useState(false)
  const [position, setPosition] = useState(0)
  const [question, setQuestion] = useState('')
  const audio = useRef<HTMLAudioElement>(null)
  const stopAt = useRef<number | null>(null)
  const uploadInput = useRef<HTMLInputElement>(null)
  const selectedNote = detail?.notes.find(note => note.id === noteId) ?? detail?.notes[0]
  const currentCourse = courses.find(course => course.id === courseId)
  const activeJob = detail?.jobs.find(job => ['queued', 'running'].includes(job.state))
  const visibleTranscript = showNoteSource && source ? source : detail?.transcript

  const run = useCallback(async (work: () => Promise<void>) => {
    setError(''); setSuccess(''); setBusy(true)
    try { await work() } catch (error) { setError(error instanceof Error ? error.message : '操作失败') } finally { setBusy(false) }
  }, [])

  const refreshCourses = useCallback(async () => {
    const list = await api<Course[]>('/courses')
    setCourses(list)
    setCourseId(previous => list.some(course => course.id === previous) ? previous : list.find(course => course.id === savedWorkspace.courseId)?.id ?? list[0]?.id ?? '')
    if (!list.length) saveWorkspace({ courseId: '', lectureId: '' })
  }, [savedWorkspace.courseId])
  const refreshDetail = useCallback(async () => {
    if (lectureId) {
      const result = await api<Detail>(`/lectures/${lectureId}`)
      if (currentLectureId.current === lectureId) setDetail(result)
    }
  }, [lectureId])

  useEffect(() => { void run(async () => { await refreshCourses(); setSettings(await api('/settings')) }) }, [refreshCourses, run])
  useEffect(() => {
    let active = true
    setLectures([]); setLectureId(''); setDetail(null)
    if (courseId) api<Lecture[]>(`/courses/${courseId}/lectures`).then(list => {
      if (!active) return
      loadedCourse.current = courseId
      setLectures(list)
      if (restorePending.current) {
        restorePending.current = false
        if (savedWorkspace.courseId === courseId && list.some(lecture => lecture.id === savedWorkspace.lectureId)) setLectureId(savedWorkspace.lectureId)
      }
    }).catch(error => { if (active) setError(error.message) })
    return () => { active = false }
  }, [courseId, savedWorkspace])
  useEffect(() => {
    if (courseId && loadedCourse.current === courseId) saveWorkspace({ courseId, lectureId })
  }, [courseId, lectureId, lectures])
  useEffect(() => {
    let active = true
    setDetail(null); setDirty({}); setNoteDirty(false); setNoteEdits({}); setNoteId(''); setPosition(0); setSource(null); setShowNoteSource(false)
    if (lectureId) api<Detail>(`/lectures/${lectureId}`).then(value => { if (active) setDetail(value) }).catch(error => { if (active) setError(error.message) })
    return () => { active = false }
  }, [lectureId])
  useEffect(() => {
    if (!activeJob) return
    const timer = window.setInterval(() => { void refreshDetail().catch(error => setError(error.message)) }, 2000)
    return () => window.clearInterval(timer)
  }, [activeJob?.id, refreshDetail])
  useEffect(() => {
    let active = true
    if (!selectedNote || selectedNote.transcript_id === detail?.transcript?.id) { setSource(detail?.transcript ?? null); return }
    api<Transcript>(`/lectures/${lectureId}/transcript?version_id=${selectedNote.transcript_id}`).then(value => { if (active) setSource(value) }).catch(error => { if (active) setError(error.message) })
    return () => { active = false }
  }, [selectedNote?.id, selectedNote?.transcript_id, detail?.transcript, lectureId])
  useEffect(() => {
    if (!noteId && detail?.notes[0]) setNoteId(detail.notes[0].id)
  }, [noteId, detail?.notes])
  useEffect(() => {
    if (!noteDirty && !bodyDirty) {
      setUserText(selectedNote?.user_markdown ?? '')
      noteVersion.current = selectedNote ? { id: selectedNote.id, edit_version: selectedNote.edit_version } : null
    }
  }, [selectedNote?.id, selectedNote?.edit_version, noteDirty, bodyDirty])

  function navigate(next: () => void) {
    if ((noteDirty || bodyDirty || Object.keys(dirty).length) && !window.confirm('有未保存的修改，确定放弃并切换吗？')) return
    setDirty({}); setNoteDirty(false); setNoteEdits({}); next()
  }
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => { if (noteDirty || bodyDirty || Object.keys(dirty).length) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [noteDirty, bodyDirty, dirty])

  async function createCourse(event: React.FormEvent) {
    event.preventDefault()
    await run(async () => {
      const course = await api<Course>('/courses', { method: 'POST', body: JSON.stringify({ name: courseName }) })
      setCourses(previous => [...previous, course]); setCourseId(course.id); setCourseName(''); setShowCourse(false)
    })
  }
  async function upload(file: File | undefined) {
    if (!file) return
    if (!courseId) { setShowCourse(true); setError('先创建一门课程，再导入录音'); return }
    if (file.size > 500 * 1024 ** 2) { setError('文件超过 500MB'); return }
    await run(async () => {
      const form = new FormData(); form.append('file', file)
      const lecture = await api<Lecture>(`/courses/${courseId}/lectures`, { method: 'POST', body: form })
      setLectures(previous => [lecture, ...previous]); setLectureId(lecture.id)
    })
  }
  async function startNotes() {
    if (!detail?.transcript) return
    await api(`/lectures/${lectureId}/notes`, { method: 'POST', body: JSON.stringify({ transcript_id: detail.transcript.id, provider, consent, api_revision: provider === 'api' ? settings?.notes_api.revision : '' }) })
    await refreshDetail()
  }
  function seek(segment: Segment) {
    if (!audio.current) return
    audio.current.currentTime = segment.start_ms / 1000
    stopAt.current = segment.end_ms / 1000
    setPosition(segment.start_ms)
    void audio.current.play().catch(() => setError('播放失败，请检查媒体文件或使用播放器手动播放'))
  }
  function updateTime() {
    if (!audio.current) return
    setPosition(audio.current.currentTime * 1000)
    if (stopAt.current !== null && audio.current.currentTime >= stopAt.current) { audio.current.pause(); stopAt.current = null }
  }
  async function saveTranscript() {
    if (!detail?.transcript) return
    await api(`/lectures/${lectureId}/transcript`, { method: 'PATCH', body: JSON.stringify({ base_version_id: dirtyVersion.current, edits: dirty }) })
    setDirty({}); await refreshDetail(); setSuccess('转录已保存为新版本，识别原文已保留')
  }
  async function saveNote() {
    if (!selectedNote || !noteVersion.current) return
    await api(`/notes/${selectedNote.id}`, { method: 'PUT', body: JSON.stringify({ markdown: userText, text_edits: noteEdits, edit_version: noteVersion.current.edit_version }) })
    setNoteDirty(false); setNoteEdits({}); await refreshDetail(); setSuccess('笔记修改已保存，原始正文和引用已保留')
  }
  async function openDemo() {
    const result = await api<{ course_id: string; lecture_id: string }>('/demo', { method: 'POST' })
    const list = await api<Course[]>('/courses'); setCourses(list)
    setCourseId(result.course_id)
    // Course changes clear the previous selection; open the example after its list loads.
    setSuccess('演示已创建，请在左侧选择「事务与课堂笔记 · 示例」')
  }
  async function removeLecture() {
    if (!window.confirm('删除这段录音及全部转录、笔记和标记？此操作无法恢复。')) return
    await api(`/lectures/${lectureId}`, { method: 'DELETE' })
    setLectures(previous => previous.filter(item => item.id !== lectureId)); setLectureId(''); setDetail(null)
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/" onClick={event => { event.preventDefault(); navigate(() => setLectureId('')) }}><span className="brand-mark"><AudioLines size={22} /></span><span>ClassEcho<small>让课堂有迹可循</small></span></a>
      <div className="sidebar-label">我的学习空间 <button aria-label="新建课程" onClick={() => setShowCourse(true)}><Plus size={16} /></button></div>
      <nav className="courses">{courses.map(course => <button className={course.id === courseId ? 'selected' : ''} key={course.id} onClick={() => navigate(() => setCourseId(course.id))}><BookOpen size={16} /><span>{course.name}</span></button>)}</nav>
      <div className="sidebar-label recordings-label">课程录音 <span>{lectures.length.toString().padStart(2, '0')}</span></div>
      <div className="lecture-list">{lectures.map(lecture => <button className={`lecture-link ${lecture.id === lectureId ? 'selected' : ''}`} key={lecture.id} onClick={() => navigate(() => setLectureId(lecture.id))}><FileAudio size={17} /><span><strong>{lecture.title}</strong><small>{timeLabel(lecture.duration * 1000)}{lecture.is_demo ? ' · 预生成示例' : ' · 本地录音'}</small></span></button>)}{!lectures.length && <p className="sidebar-empty">这里还没有录音<br />从一段课堂声音开始</p>}</div>
      <div className="sidebar-bottom"><div className="privacy"><ShieldCheck size={17} /><span>音频留在本机<small>本地转录 · 自主核对</small></span></div><button className="settings-button" onClick={() => { setShowSettings(true); void api<Settings>('/settings').then(setSettings).catch(error => setError(error.message)) }}><Settings2 size={16} />设置</button><span className="version">ClassEcho · 本地预览 v0.1</span></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb"><BookOpen size={15} />{currentCourse?.name ?? '我的学习空间'}<span>/</span><strong>{detail?.title ?? '课程概览'}</strong></div><button className="button primary" disabled={busy} onClick={() => courseId ? uploadInput.current?.click() : setShowCourse(true)}><Plus size={16} />导入录音</button><input ref={uploadInput} type="file" accept=".mp3,.m4a,.wav,.mp4" hidden onChange={event => { void upload(event.target.files?.[0]); event.target.value = '' }} /></header>
      {(error || success) && <div role={error ? 'alert' : 'status'} className={`notice ${error ? 'error' : ''}`}><span>{error || success}</span><button aria-label="关闭提示" onClick={() => { setError(''); setSuccess('') }}><X size={16} /></button></div>}
      {!detail ? <div className="overview">
        <div className="overview-title"><span className="eyebrow">A LITTLE LESS WRITING. A LITTLE MORE LEARNING.</span><h1>把课堂留下来，<br /><em>让理解慢慢发生。</em></h1><p>从一段录音开始，把来不及记下的内容<br />整理成有原文、有出处、能回听的课堂笔记。</p></div>
        <div className="import-card" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void upload(event.dataTransfer.files[0]) }}><div className="upload-icon"><Upload size={26} /></div><h2>导入你的第一段课堂录音</h2><p>拖入文件，或选择一段电脑上的录音</p><button className="button primary" disabled={busy} onClick={() => courseId ? uploadInput.current?.click() : setShowCourse(true)}>{busy ? <LoaderCircle className="spin" size={16} /> : <FileAudio size={16} />}选择音视频文件</button><small>MP3 / M4A / WAV / MP4 · 最大 500MB · 最长 90 分钟</small></div>
        <button className="demo-link" disabled={busy} onClick={() => void run(openDemo)}><Headphones size={17} />先体验一段预生成示例<span>无需 API 密钥 →</span></button>
        <div className="feature-strip"><div><span>01</span><strong>本地转录</strong><p>原始音频保存在你的电脑</p></div><div><span>02</span><strong>核对再整理</strong><p>先修正术语，再组织笔记</p></div><div><span>03</span><strong>每条都能回听</strong><p>从笔记找到对应的课堂原文</p></div></div>
      </div> : <>
        <div className="lecture-header"><button className="back-button" onClick={() => navigate(() => setLectureId(''))}><ArrowLeft size={14} />课程概览</button><div className="lecture-title-row"><div><span className="eyebrow">LECTURE WORKSPACE</span><h1>{detail.title}</h1><div className="metadata"><span><Clock3 size={13} />{timeLabel(detail.duration * 1000)}</span><span><ShieldCheck size={13} />本地保存</span>{detail.is_demo && <span className="tag">预生成示例</span>}</div></div><button className="icon-button danger" aria-label="删除录音" disabled={busy || !!activeJob} onClick={() => void run(removeLecture)}><Trash2 size={17} /></button></div></div>
        <div className="work-toolbar"><div><select aria-label="转录模型" value={model} onChange={event => setModel(event.target.value)}><option value="small">Whisper small · 轻量基线</option><option value="turbo">Whisper turbo · 质量对照</option></select><button className="button" disabled={busy || !!activeJob} onClick={() => void run(async () => { await api(`/lectures/${lectureId}/transcribe`, { method: 'POST', body: JSON.stringify({ model, force: !!detail.transcript }) }); await refreshDetail() })}><AudioLines size={15} />{detail.transcript ? '重新转录' : '开始本地转录'}</button></div><div><select aria-label="笔记方式" value={provider} onChange={event => { setProvider(event.target.value); setConsent(false) }}><option value="extractive">本地逐段摘录（非 AI）</option><option value="api">AI 接口整理</option></select><button className="button primary" disabled={busy || !!activeJob || !detail.transcript || Object.keys(dirty).length > 0 || (provider === 'api' && (!consent || !settings?.notes_api?.configured))} onClick={() => void run(startNotes)}><Sparkles size={15} />整理笔记</button></div></div>
        {provider === 'api' && <div className="cloud-consent"><label><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />将当前转录文字发送至 {settings?.notes_api?.base_url || '你配置的接口'}，不发送音频。</label>{!settings?.notes_api?.configured && <span>请在左侧「设置」中填写 API URL、模型和密钥。</span>}</div>}
        {activeJob && <JobStatus job={activeJob} onCancel={() => void run(async () => { await api(`/jobs/${activeJob.id}/cancel`, { method: 'POST' }); await refreshDetail() })} />}
        {!activeJob && detail.jobs[0]?.state === 'failed' && <div className="job-status failed"><CircleHelp size={17} /><span>{detail.jobs[0].error}</span><button onClick={() => void run(async () => { await api(`/jobs/${detail.jobs[0].id}/retry`, { method: 'POST' }); await refreshDetail() })}><RotateCcw size={14} />重试失败阶段</button></div>}
        <div className="workspace">
          <section className="notes-pane"><div className="pane-heading"><div><span className="eyebrow">YOUR KNOWLEDGE, WITH CONTEXT</span><h2>课堂笔记</h2></div><div className="export-links"><a title="导出 Markdown" aria-label="导出 Markdown" href={`/api/lectures/${lectureId}/export?format=markdown${selectedNote ? `&note_id=${selectedNote.id}` : ''}`}><ArrowDownToLine size={16} />MD</a><a href={`/api/lectures/${lectureId}/export?format=srt`}>SRT</a><a href={`/api/lectures/${lectureId}/export?format=json`}>JSON</a></div></div>
          {detail.notes.length > 0 && <div className="note-version"><select aria-label="笔记版本" value={selectedNote?.id} onChange={event => navigate(() => setNoteId(event.target.value))}>{detail.notes.map((note, index) => <option key={note.id} value={note.id}>笔记版本 {detail.notes.length - index} · {new Date(note.created_at).toLocaleString('zh-CN')}</option>)}</select><ChevronDown size={13} /></div>}
          {selectedNote ? <>
            {noteIsStale(selectedNote.transcript_id, detail.active_transcript_id) && <div className="stale-warning">这份笔记基于旧转录。引用仍回到旧版原文；可基于当前转录重新生成，旧笔记和用户修改会保留。</div>}
            <div className="note-kind"><span className="status-dot" />{selectedNote.provider === 'api' ? `AI 整理 · ${selectedNote.model} · 引用需核对` : selectedNote.provider === 'qwen' ? 'Qwen 整理 · 引用需核对' : '本地逐段摘录 / 预生成示例 · 非 AI 摘要'}</div>
            <NoteContent key={selectedNote.id} note={selectedNote} segments={source?.segments ?? []} drafts={noteEdits} busy={busy} onEdit={(key, text) => setNoteEdits(previous => ({ ...previous, [key]: text }))} onSave={() => void run(saveNote)} onDiscard={() => setNoteEdits({})} onSeek={segment => { setShowNoteSource(source?.id !== detail.transcript?.id); seek(segment) }} />
            <div className="user-notes"><div><h3><FileText size={16} />我的补充</h3><button className="button small" disabled={!noteDirty || busy} onClick={() => void run(saveNote)}><Check size={14} />保存笔记</button></div><p>你的补充单独保存，重新整理不会覆盖。</p><textarea aria-label="我的补充笔记" placeholder="写下自己的理解、疑问，或粘贴 Markdown 笔记…" value={userText} onChange={event => { setUserText(event.target.value); setNoteDirty(true) }} /></div>
          </> : <div className="pane-empty"><FileText size={36} strokeWidth={1.2} /><h3>从听懂，到记住</h3><p>{detail.transcript ? '先核对右侧转录，再点击「整理笔记」。' : '先完成本地转录，笔记就从这里开始。'}</p></div>}
          <div className="bookmarks"><h3><CircleHelp size={15} />没听懂的地方</h3><form onSubmit={event => { event.preventDefault(); void run(async () => { await api(`/lectures/${lectureId}/bookmarks`, { method: 'POST', body: JSON.stringify({ position_ms: Math.round(position), question }) }); setQuestion(''); await refreshDetail() }) }}><input aria-label="回听疑问" value={question} onChange={event => setQuestion(event.target.value)} placeholder={`在 ${timeLabel(position)} 记下疑问…`} maxLength={2000} required /><button className="icon-button" aria-label="保存疑问" disabled={busy}><Plus size={17} /></button></form>{detail.bookmarks.map(mark => <div className="bookmark" key={mark.id}><button onClick={() => seek({ id: '', raw_text: '', text: '', start_ms: mark.position_ms, end_ms: Math.min(mark.position_ms + 15000, detail.duration * 1000) })}>{timeLabel(mark.position_ms)}</button><span>{mark.question}</span><button aria-label="删除疑问" onClick={() => void run(async () => { await api(`/bookmarks/${mark.id}`, { method: 'DELETE' }); await refreshDetail() })}><X size={13} /></button></div>)}</div>
          </section>
          <aside className="transcript-pane">{visibleTranscript ? <>{visibleTranscript.id !== detail.transcript?.id && <div className="edit-bar">引用的旧转录 · 只读<button onClick={() => setShowNoteSource(false)}>返回当前版本</button></div>}<TranscriptPane segments={visibleTranscript.segments} current={position} dirty={visibleTranscript.id === detail.transcript?.id ? dirty : {}} readOnly={visibleTranscript.id !== detail.transcript?.id} onSeek={seek} onEdit={(id, value) => { if (!Object.keys(dirty).length) dirtyVersion.current = visibleTranscript!.id; setDirty(previous => ({ ...previous, [id]: value })) }} onSave={() => void run(saveTranscript)} onDiscard={() => setDirty({})} /><div className="transcript-footer">{visibleTranscript.engine} · {visibleTranscript.metrics.elapsed_seconds ? `耗时 ${visibleTranscript.metrics.elapsed_seconds.toFixed(1)} 秒` : '预生成转录'}<br />双击文字可修订，原始识别结果会保留。</div></> : <><div className="pane-heading"><div><span className="eyebrow">TRANSCRIPT</span><h2>课堂原文</h2></div><AudioLines size={17} /></div><div className="pane-empty"><AudioLines size={36} strokeWidth={1.2} /><h3>等待第一段文字</h3><p>点击上方「开始本地转录」。<br />首次使用需要下载模型。</p></div></>}</aside>
        </div>
        <footer className="player"><div className="player-title"><span><Headphones size={19} /></span><div><strong>{detail.title}</strong><small>原始录音 · {timeLabel(position)} / {timeLabel(detail.duration * 1000)}</small></div></div><audio key={lectureId} ref={audio} controls preload="metadata" src={`/api/lectures/${lectureId}/media`} onTimeUpdate={updateTime} onSeeking={() => { if (audio.current && stopAt.current !== null && audio.current.currentTime > stopAt.current) stopAt.current = null }} /><label className="speed-select">倍速<select aria-label="播放速度" defaultValue="1" onChange={event => { if (audio.current) audio.current.playbackRate = Number(event.target.value) }}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label></footer>
      </>}
    </main>
    {showCourse && <div className="modal-backdrop"><form className="modal" onSubmit={createCourse}><div className="modal-title"><h2>新建课程</h2><button type="button" aria-label="关闭新建课程" onClick={() => setShowCourse(false)}><X size={19} /></button></div><p>给相关录音一个共同的归属。</p><label>课程名称<input autoFocus placeholder="例如：数据库原理" value={courseName} onChange={event => setCourseName(event.target.value)} maxLength={120} required /></label><button className="button primary" disabled={busy || !courseName.trim()}>创建课程</button></form></div>}
    {showSettings && <div className="modal-backdrop"><section className="modal settings-modal"><div className="modal-title"><h2>设置</h2><button aria-label="关闭设置" onClick={() => setShowSettings(false)}><X size={19} /></button></div><div className="setting-block"><h3>本地转录</h3>{settings?.models.map(item => <p key={item.name}>{item.name}<span className="tag">{item.ready ? '模型已就绪' : '首次转录时下载'}</span></p>)}</div>{settings?.notes_api && <APISettings config={settings.notes_api} onSaved={config => { setSettings(previous => previous ? { ...previous, notes_api: config } : previous); setConsent(false) }} />}</section></div>}
    {busy && <div className="working"><LoaderCircle className="spin" size={16} />正在处理…</div>}
  </div>
}

function JobStatus({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  return <div className="job-status"><LoaderCircle className="spin" size={17} /><span>{stageNames[job.stage] ?? job.stage}{job.stage === 'draft' && job.checkpoint?.notes_progress && ` · 已完成 ${job.checkpoint.notes_progress.completed}/${job.checkpoint.notes_progress.total} 段`}</span><small>已用 {timeLabel(now - new Date(job.created_at).getTime())} · 关闭页面不会取消任务</small>{job.state === 'queued' && <button onClick={onCancel}>取消排队</button>}</div>
}
