import { BookOpen, FileAudio, FileText, Plus, X } from 'lucide-react'
import { timeLabel } from './api'
import type { Course, Lecture } from './types'

export default function WorkspaceSidebar({ courses, courseId, lectures, lectureId, onHome, onCourse, onLecture, onNewCourse, onClose }: {
  courses: Course[]; courseId: string; lectures: Lecture[]; lectureId: string
  onHome: () => void; onCourse: (id: string) => void; onLecture: (id: string) => void
  onNewCourse: () => void; onClose: () => void
}) {
  return <aside className="sidebar" aria-label="课程列表">
    <div className="sidebar-brand"><button className="brand" onClick={onHome}><FileText size={19} /><span>ClassEcho</span></button><button className="sidebar-close icon-button" aria-label="关闭课程列表" onClick={onClose}><X size={17} /></button></div>
    <div className="sidebar-label"><span>课程</span><button aria-label="新建课程" title="新建课程" onClick={onNewCourse}><Plus size={16} /></button></div>
    <nav className="courses" aria-label="课程">{courses.map(course => <button key={course.id} className={course.id === courseId ? 'selected' : ''} onClick={() => onCourse(course.id)}><BookOpen size={15} /><span>{course.name}</span></button>)}</nav>
    <div className="sidebar-label recordings-label"><span>录音</span><span>{lectures.length}</span></div>
    <nav className="lecture-list" aria-label="录音">{lectures.map(lecture => <button key={lecture.id} className={`lecture-link ${lecture.id === lectureId ? 'selected' : ''}`} onClick={() => onLecture(lecture.id)}><FileAudio size={15} /><span><strong>{lecture.title}</strong><small>{timeLabel(lecture.duration * 1000)}{lecture.is_demo ? ' · 示例' : ''}</small></span></button>)}{!lectures.length && <p className="sidebar-empty">暂无录音</p>}</nav>
    <div className="sidebar-bottom"><span className="local-indicator" /><span>本地工作区</span><small>v0.1</small></div>
  </aside>
}
