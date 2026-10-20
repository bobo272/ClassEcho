import { useCallback, useEffect, useRef, useState } from 'react'
import { AudioLines, ArrowDownToLine, BookOpen, Check, ChevronDown, CircleHelp, Clock3, FileText, Headphones, LoaderCircle, Mic, PanelLeft, PanelRight, Plus, RotateCcw, Settings2, SlidersHorizontal, Sparkles, Trash2, X } from 'lucide-react'
import { api, noteIsStale, timeLabel } from './api'
import type { Course, Detail, Job, Lecture, Note, Segment, Settings, Transcript } from './types'
import TranscriptPane from './TranscriptPane'
import APISettings from './APISettings'
import NoteContent from './NoteContent'
import { readWorkspace, saveWorkspace } from './workspace'
import WorkspaceSidebar from './WorkspaceSidebar'
import LibraryOverview from './LibraryOverview'
import Dialog from './Dialog'
import MicrophoneRecorder from './MicrophoneRecorder'

const stageNames: Record<string, string> = { queued: '等待处理', normalize: '规范化音频', download: '检查或下载模型（首次较慢）', transcribe: '本地转录中', draft: '整理笔记中', validate: '检查来源引用', complete: '已完成' }

export default function App() {
  const [savedWorkspace] = useState(readWorkspace)
  const restorePending = useRef(true)
  const pendingOpen = useRef<{ courseId: string; lectureId: string } | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 1000)
  const [showTranscript, setShowTranscript] = useState(false)
  const [showPlayer, setShowPlayer] = useState(false)
  const [showTools, setShowTools] = useState(false)
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
  const [showRecording, setShowRecording] = useState(false)
  const recordingUpload = useRef<Lecture | null>(null)
  const [courseName, setCourseName] = useState('')
  const [model, setModel] = useState('small')
  const [provider, setProvider] = useState('extractive')
  const [consent, setConsent] = useState(false)
  const [dirty, setDirty] = useState<Record<string, string>>({})
  const dirtyVersion = useRef<string | null>(null)
  const [noteId, setNoteId] = useState('')
  const pendingNoteJob = useRef<string | null>(null)
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
  const hasCurrentNote = detail?.notes.some(note => note.transcript_id === detail.transcript?.id && note.provider === provider) ?? false
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
      if (pendingOpen.current?.courseId === courseId && list.some(lecture => lecture.id === pendingOpen.current?.lectureId)) {
        setLectureId(pendingOpen.current.lectureId); pendingOpen.current = null; restorePending.current = false
      }
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
    pendingNoteJob.current = null
    setShowTranscript(false); setShowPlayer(false); setShowTools(false); stopAt.current = null
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
    if (!detail || detail.id !== lectureId) return
    const running = detail.jobs.find(job => job.kind === 'notes' && ['queued', 'running'].includes(job.state))
    if (!pendingNoteJob.current && running) pendingNoteJob.current = running.id
    const finished = detail.jobs.find(job => job.id === pendingNoteJob.current)
    if (finished?.state === 'succeeded' && finished.result_id && !noteDirty && !bodyDirty && detail.notes.some(note => note.id === finished.result_id)) {
      setNoteId(finished.result_id); pendingNoteJob.current = null
    } else if (finished && ['failed', 'cancelled'].includes(finished.state)) pendingNoteJob.current = null
  }, [detail, lectureId, noteDirty, bodyDirty])
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

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || showSettings || showCourse || showRecording) return
      if (showTranscript) setShowTranscript(false)
      else if (sidebarOpen && window.innerWidth < 1000) setSidebarOpen(false)
    }
    document.addEventListener('keydown', keydown)
    return () => document.removeEventListener('keydown', keydown)
  }, [showSettings, showCourse, showRecording, showTranscript, sidebarOpen])

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
    const job = await api<Job>(`/lectures/${lectureId}/notes`, { method: 'POST', body: JSON.stringify({ transcript_id: detail.transcript.id, provider, consent, force: hasCurrentNote, api_revision: provider === 'api' ? settings?.notes_api.revision : '' }) })
    pendingNoteJob.current = job.id
    await refreshDetail()
  }
  function seek(segment: Segment) {
    setShowPlayer(true)
    if (segment.id) setShowTranscript(true)
    if (!audio.current) return
    audio.current.currentTime = segment.start_ms / 1000
    stopAt.current = segment.end_ms / 1000
    setPosition(segment.start_ms)
    void audio.current.play().catch(() => setError('播放失败，请检查媒体文件或使用播放器手动播放'))
  }
  function closePlayer() {
    audio.current?.pause(); setShowPlayer(false); stopAt.current = null
  }
  function openSettings() {
    setShowSettings(true)
    void api<Settings>('/settings').then(setSettings).catch(error => setError(error.message))
  }
  function chooseLecture(id: string) {
    navigate(() => { setLectureId(id); if (window.innerWidth < 1000) setSidebarOpen(false) })
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
    pendingOpen.current = { courseId: result.course_id, lectureId: result.lecture_id }
    if (courseId === result.course_id) { setLectureId(result.lecture_id); pendingOpen.current = null } else setCourseId(result.course_id)
    if (window.innerWidth < 1000) setSidebarOpen(false)
  }
  async function removeLecture() {
    if (!window.confirm('删除这段录音及全部转录、笔记和标记？此操作无法恢复。')) return
    await api(`/lectures/${lectureId}`, { method: 'DELETE' })
    setLectures(previous => previous.filter(item => item.id !== lectureId)); setLectureId(''); setDetail(null)
  }

  return <div className={`app-shell ${sidebarOpen ? 'with-sidebar' : ''} ${showTranscript ? 'with-transcript' : ''} ${showPlayer ? 'with-player' : ''}`}>
    {sidebarOpen && <><div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} /><WorkspaceSidebar courses={courses} courseId={courseId} lectures={lectures} lectureId={lectureId} onHome={() => navigate(() => setLectureId(''))} onCourse={id => navigate(() => { setCourseId(id); if (window.innerWidth < 1000) setSidebarOpen(false) })} onLecture={chooseLecture} onNewCourse={() => setShowCourse(true)} onClose={() => setSidebarOpen(false)} /></>}
    <main className="main">
      <header className="topbar"><div className="topbar-start"><button className="icon-button" aria-label={sidebarOpen ? '收起课程列表' : '展开课程列表'} aria-expanded={sidebarOpen} onClick={() => setSidebarOpen(!sidebarOpen)}><PanelLeft size={18} /></button><div className="breadcrumb"><BookOpen size={14} /><button onClick={() => navigate(() => setLectureId(''))}>{currentCourse?.name ?? '我的笔记'}</button>{detail && <><span>/</span><strong>{detail.title}</strong></>}</div></div><div className="topbar-actions"><button className="button recording-entry" disabled={busy} aria-label="麦克风录音" onClick={() => navigate(() => { if (!courseId) { setShowCourse(true); return }; recordingUpload.current = null; setShowRecording(true); void api<Settings>('/settings').then(setSettings).catch(error => setError(error.message)) })}><Mic size={15} /><span>录音</span></button><button className="button" disabled={busy} onClick={() => courseId ? uploadInput.current?.click() : setShowCourse(true)}><Plus size={15} /><span>导入录音</span></button><button className="icon-button" aria-label="设置" title="设置" onClick={openSettings}><Settings2 size={18} /></button></div><input ref={uploadInput} type="file" accept=".mp3,.m4a,.wav,.mp4,.webm" hidden onChange={event => { void upload(event.target.files?.[0]); event.target.value = '' }} /></header>
      {(error || success) && <div role={error ? 'alert' : 'status'} className={`notice ${error ? 'error' : ''}`}><span>{error || success}</span><button aria-label="关闭提示" onClick={() => { setError(''); setSuccess('') }}><X size={16} /></button></div>}
      {!detail ? <LibraryOverview courseName={currentCourse?.name ?? '我的笔记'} lectures={lectures} busy={busy} onOpen={chooseLecture} onImport={() => courseId ? uploadInput.current?.click() : setShowCourse(true)} onDemo={() => void run(openDemo)} onDrop={file => void upload(file)} /> : <>
        <div className="lecture-header"><div className="document-label"><FileText size={15} />课程笔记</div><div className="lecture-title-row"><h1>{detail.title}</h1><button className="icon-button danger" aria-label="删除录音" title="删除录音" disabled={busy || !!activeJob} onClick={() => void run(removeLecture)}><Trash2 size={16} /></button></div><div className="metadata"><span><Clock3 size={13} />{timeLabel(detail.duration * 1000)}</span><span>{detail.is_demo ? '预生成示例' : '本地录音'}</span><span>{detail.notes.length} 个笔记版本</span></div>
        <div className="document-actions"><button className={`button ${showTools ? 'selected' : ''}`} aria-expanded={showTools} onClick={() => setShowTools(!showTools)}><SlidersHorizontal size={15} />转录与整理</button><div><button className={`button ${showTranscript ? 'selected' : ''}`} aria-label="课堂原文" aria-controls="classecho-transcript" aria-expanded={showTranscript} onClick={() => setShowTranscript(!showTranscript)}><PanelRight size={15} />课堂原文</button><button className={`button ${showPlayer ? 'selected' : ''}`} aria-label="播放器" aria-controls="classecho-player" aria-expanded={showPlayer} onClick={() => showPlayer ? closePlayer() : setShowPlayer(true)}><Headphones size={15} />播放录音</button></div></div></div>
        <div className="work-toolbar" hidden={!showTools}><div><select aria-label="转录模型" value={model} onChange={event => setModel(event.target.value)}><option value="small">Whisper small · 轻量基线</option><option value="turbo">Whisper turbo · 质量对照</option></select><button className="button" disabled={busy || !!activeJob} onClick={() => void run(async () => { await api(`/lectures/${lectureId}/transcribe`, { method: 'POST', body: JSON.stringify({ model, force: !!detail.transcript }) }); await refreshDetail() })}><AudioLines size={15} />{detail.transcript ? '重新转录' : '开始本地转录'}</button></div><div><select aria-label="笔记方式" value={provider} onChange={event => { setProvider(event.target.value); setConsent(false) }}><option value="extractive">本地逐段摘录（非 AI）</option><option value="api">AI 接口整理</option></select><button className="button primary" disabled={busy || !!activeJob || noteDirty || bodyDirty || !detail.transcript || Object.keys(dirty).length > 0 || (provider === 'api' && (!consent || !settings?.notes_api?.configured))} onClick={() => void run(startNotes)}><Sparkles size={15} />{hasCurrentNote ? '重新整理' : '整理笔记'}</button></div></div>
        {(noteDirty || bodyDirty) && <p className="cloud-consent">请先保存或放弃笔记修改，再整理新版本。</p>}
        {showTools && provider === 'api' && <div className="cloud-consent"><label><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />将当前转录文字发送至 {settings?.notes_api?.base_url || '你配置的接口'}，不发送音频。</label>{!settings?.notes_api?.configured && <span>请在左侧「设置」中填写 API URL、模型和密钥。</span>}</div>}
        {activeJob && <JobStatus job={activeJob} onCancel={() => void run(async () => { await api(`/jobs/${activeJob.id}/cancel`, { method: 'POST' }); await refreshDetail() })} />}
        {!activeJob && detail.jobs[0]?.state === 'failed' && <div className="job-status failed"><CircleHelp size={17} /><span>{detail.jobs[0].error}</span><button onClick={() => void run(async () => { await api(`/jobs/${detail.jobs[0].id}/retry`, { method: 'POST' }); await refreshDetail() })}><RotateCcw size={14} />重试失败阶段</button></div>}
        <div className="workspace">
          <section className="notes-pane"><div className="pane-heading"><div><h2>课堂笔记</h2>{selectedNote && <span className="save-state">{bodyDirty || noteDirty ? '未保存' : '已保存'}</span>}</div><div className="export-links"><a title="导出 Markdown" aria-label="导出 Markdown" href={`/api/lectures/${lectureId}/export?format=markdown${selectedNote ? `&note_id=${selectedNote.id}` : ''}`}><ArrowDownToLine size={16} />Markdown</a><a href={`/api/lectures/${lectureId}/export?format=srt`}>SRT</a><a href={`/api/lectures/${lectureId}/export?format=json`}>JSON</a></div></div>
          {detail.notes.length > 0 && <div className="note-version"><select aria-label="笔记版本" value={selectedNote?.id} onChange={event => navigate(() => setNoteId(event.target.value))}>{detail.notes.map((note, index) => <option key={note.id} value={note.id}>笔记版本 {detail.notes.length - index} · {new Date(note.created_at).toLocaleString('zh-CN')}</option>)}</select><ChevronDown size={13} /></div>}
          {selectedNote ? <>
            {noteIsStale(selectedNote.transcript_id, detail.active_transcript_id) && <div className="stale-warning">这份笔记基于旧转录。引用仍回到旧版原文；可基于当前转录重新生成，旧笔记和用户修改会保留。</div>}
            <div className="note-kind"><span className="status-dot" />{selectedNote.provider === 'api' ? `AI 整理 · ${selectedNote.model} · 引用需核对` : selectedNote.provider === 'qwen' ? 'Qwen 整理 · 引用需核对' : '本地摘录 · 非 AI'}</div>
            <NoteContent key={selectedNote.id} note={selectedNote} segments={source?.segments ?? []} drafts={noteEdits} busy={busy} onEdit={(key, text) => setNoteEdits(previous => ({ ...previous, [key]: text }))} onSave={() => void run(saveNote)} onDiscard={() => setNoteEdits({})} onSeek={segment => { setShowNoteSource(source?.id !== detail.transcript?.id); seek(segment) }} />
            <div className="user-notes"><div><h3><FileText size={16} />我的补充</h3><button className="button small" disabled={!noteDirty || busy} onClick={() => void run(saveNote)}><Check size={14} />保存笔记</button></div><p>你的补充单独保存，重新整理不会覆盖。</p><textarea aria-label="我的补充笔记" placeholder="写下自己的理解、疑问，或粘贴 Markdown 笔记…" value={userText} onChange={event => { setUserText(event.target.value); setNoteDirty(true) }} /></div>
          </> : <div className="pane-empty"><FileText size={36} strokeWidth={1.2} /><h3>还没有笔记</h3><p>{detail.transcript ? '展开课堂原文核对文字，再从「转录与整理」生成笔记。' : '从「转录与整理」开始识别这份录音。'}</p></div>}
          <div className="bookmarks"><h3><CircleHelp size={15} />没听懂的地方</h3><form onSubmit={event => { event.preventDefault(); void run(async () => { await api(`/lectures/${lectureId}/bookmarks`, { method: 'POST', body: JSON.stringify({ position_ms: Math.round(position), question }) }); setQuestion(''); await refreshDetail() }) }}><input aria-label="回听疑问" value={question} onChange={event => setQuestion(event.target.value)} placeholder={`在 ${timeLabel(position)} 记下疑问…`} maxLength={2000} required /><button className="icon-button" aria-label="保存疑问" disabled={busy}><Plus size={17} /></button></form>{detail.bookmarks.map(mark => <div className="bookmark" key={mark.id}><button onClick={() => seek({ id: '', raw_text: '', text: '', start_ms: mark.position_ms, end_ms: Math.min(mark.position_ms + 15000, detail.duration * 1000) })}>{timeLabel(mark.position_ms)}</button><span>{mark.question}</span><button aria-label="删除疑问" onClick={() => void run(async () => { await api(`/bookmarks/${mark.id}`, { method: 'DELETE' }); await refreshDetail() })}><X size={13} /></button></div>)}</div>
          </section>
          <aside id="classecho-transcript" className="transcript-pane" aria-label="课堂原文面板" hidden={!showTranscript}><div className="inspector-bar"><span>原文核对</span><button className="icon-button" aria-label="关闭课堂原文" onClick={() => setShowTranscript(false)}><X size={17} /></button></div>{visibleTranscript ? <>{visibleTranscript.id !== detail.transcript?.id && <div className="edit-bar">引用的旧转录 · 只读<button onClick={() => setShowNoteSource(false)}>返回当前版本</button></div>}<TranscriptPane segments={visibleTranscript.segments} current={position} dirty={visibleTranscript.id === detail.transcript?.id ? dirty : {}} readOnly={visibleTranscript.id !== detail.transcript?.id} onSeek={seek} onEdit={(id, value) => { if (!Object.keys(dirty).length) dirtyVersion.current = visibleTranscript!.id; setDirty(previous => ({ ...previous, [id]: value })) }} onSave={() => void run(saveTranscript)} onDiscard={() => setDirty({})} /><div className="transcript-footer">{visibleTranscript.engine} · {visibleTranscript.metrics.elapsed_seconds ? `耗时 ${visibleTranscript.metrics.elapsed_seconds.toFixed(1)} 秒` : '预生成转录'}<br />双击文字可修订，原始识别结果会保留。</div></> : <><div className="pane-heading"><div><h2>课堂原文</h2></div><AudioLines size={17} /></div><div className="pane-empty"><AudioLines size={36} strokeWidth={1.2} /><h3>等待第一段文字</h3><p>点击上方「开始本地转录」。<br />首次使用需要下载模型。</p></div></>}</aside>
        </div>
        <footer id="classecho-player" className="player" aria-label="录音播放器" hidden={!showPlayer}><div className="player-title"><span><Headphones size={19} /></span><div><strong>{detail.title}</strong><small>原始录音 · {timeLabel(position)} / {timeLabel(detail.duration * 1000)}</small></div></div><audio key={lectureId} ref={audio} controls preload="metadata" src={`/api/lectures/${lectureId}/media`} onTimeUpdate={updateTime} onSeeking={() => { if (audio.current && stopAt.current !== null && audio.current.currentTime > stopAt.current) stopAt.current = null }} /><label className="speed-select">倍速<select aria-label="播放速度" defaultValue="1" onChange={event => { if (audio.current) audio.current.playbackRate = Number(event.target.value) }}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button className="icon-button" aria-label="关闭播放器" onClick={closePlayer}><X size={17} /></button></footer>
      </>}
    </main>
    {showRecording && <MicrophoneRecorder courseName={currentCourse?.name ?? '当前课程'} liveReady={!!settings?.models.some(item => item.name === 'small' && item.ready)} notesAPI={settings?.notes_api} onClose={() => setShowRecording(false)} onSave={async (file, processing) => {
      let lecture = recordingUpload.current
      if (!lecture) {
        const form = new FormData(); form.append('file', file)
        lecture = await api<Lecture>(`/courses/${courseId}/lectures`, { method: 'POST', body: form })
        recordingUpload.current = lecture; setLectures(previous => [lecture!, ...previous])
      }
      if (processing) await api<Job>(`/lectures/${lecture.id}/transcribe`, { method: 'POST', body: JSON.stringify({ model: 'small', after_transcribe: processing }) })
      setLectureId(lecture.id); setShowRecording(false)
    }} />}
    {showCourse && <Dialog title="新建课程" closeLabel="关闭新建课程" onClose={() => setShowCourse(false)}><form className="course-form" onSubmit={createCourse}><p>同一门课程的录音与笔记保存在一起。</p><label>课程名称<input placeholder="例如：数据库原理" value={courseName} onChange={event => setCourseName(event.target.value)} maxLength={120} required /></label><button className="button primary" disabled={busy || !courseName.trim()}>创建课程</button></form></Dialog>}
    {showSettings && <Dialog title="设置" closeLabel="关闭设置" className="settings-modal" onClose={() => setShowSettings(false)}><div className="setting-block"><h3>本地转录</h3>{settings?.models.map(item => <p key={item.name}>{item.name}<span className="tag">{item.ready ? '模型已就绪' : '首次转录时下载'}</span></p>)}</div>{settings?.notes_api && <APISettings config={settings.notes_api} onSaved={config => { setSettings(previous => previous ? { ...previous, notes_api: config } : previous); setConsent(false) }} />}</Dialog>}
    {busy && <div className="working"><LoaderCircle className="spin" size={16} />正在处理…</div>}
  </div>
}

function JobStatus({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer) }, [])
  return <div className="job-status"><LoaderCircle className="spin" size={17} /><span>{stageNames[job.stage] ?? job.stage}{job.stage === 'draft' && job.checkpoint?.notes_progress && ` · 已完成 ${job.checkpoint.notes_progress.completed}/${job.checkpoint.notes_progress.total} 段`}</span><small>已用 {timeLabel(now - new Date(job.created_at).getTime())} · 关闭页面不会取消任务</small>{job.state === 'queued' && <button onClick={onCancel}>取消排队</button>}</div>
}
