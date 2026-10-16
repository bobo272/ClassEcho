import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'
import type { Detail, Note } from './types'
import { readWorkspace, saveWorkspace } from './workspace'

vi.mock('./api', async importOriginal => {
  const original = await importOriginal<typeof import('./api')>()
  return { ...original, api: vi.fn() }
})
const settings = { models: [{ name: 'small', ready: true }], notes_api: { base_url: '', model: '', configured: false, key_configured: false, revision: '' } }
function mockRoutes(extra: Record<string, unknown> = {}) {
  const routes: Record<string, unknown> = { '/courses': [], '/settings': settings, ...extra }
  vi.mocked(api).mockImplementation(async <T,>(path: string, options?: RequestInit): Promise<T> => {
    if (!(path in routes)) throw new Error(`Unexpected API path: ${path}`)
    const value = routes[path]
    return (typeof value === 'function' ? value(options) : value) as T
  })
}
beforeEach(() => { localStorage.clear(); vi.mocked(api).mockReset(); mockRoutes() })
afterEach(() => { cleanup(); vi.useRealTimers() })

it('设置保留本地模型状态，移除云端笔记与预算面板', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '设置' }))
  expect(await screen.findByText('模型已就绪')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '本地转录' })).toBeInTheDocument()
  expect(screen.getByLabelText('API URL')).toHaveValue('')
  expect(screen.queryByText('云端笔记')).not.toBeInTheDocument()
  expect(screen.queryByText(/预算 ¥/)).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /查看逐次用量记录/ })).not.toBeInTheDocument()
})

it('刷新后恢复所选课程、录音和未完成任务，只保存 ID', async () => {
  saveWorkspace({ courseId: 'c2', lectureId: 'l2' })
  const lecture = { id: 'l2', title: '待处理课程录音', duration: 30, is_demo: false, active_transcript_id: null, created_at: new Date().toISOString() }
  mockRoutes({
    '/courses': [{ id: 'c1', name: '第一门课' }, { id: 'c2', name: '第二门课' }],
    '/courses/c2/lectures': [lecture],
    '/lectures/l2': { ...lecture, transcript: null, transcript_versions: [], notes: [], bookmarks: [], jobs: [{ id: 'j1', kind: 'transcribe', state: 'queued', stage: 'queued', error: null, created_at: new Date().toISOString() }] },
  })
  const view = render(<App />)
  expect(await screen.findByRole('heading', { name: '待处理课程录音' })).toBeInTheDocument()
  expect(await screen.findByText('等待处理')).toBeInTheDocument()
  await waitFor(() => expect(readWorkspace()).toEqual({ courseId: 'c2', lectureId: 'l2' }))
  view.unmount()
  render(<App />)
  expect(await screen.findByRole('heading', { name: '待处理课程录音' })).toBeInTheDocument()
  expect(await screen.findByText('等待处理')).toBeInTheDocument()
  expect(vi.mocked(api).mock.calls.filter(([path]) => path === '/lectures/l2')).toHaveLength(2)
  expect(JSON.parse(localStorage.getItem('classecho.workspace.v1')!)).toEqual({ courseId: 'c2', lectureId: 'l2' })
})

it('已删除的录音不会被恢复，也不会请求无效详情', async () => {
  saveWorkspace({ courseId: 'c1', lectureId: 'deleted' })
  mockRoutes({ '/courses': [{ id: 'c1', name: '第一门课' }], '/courses/c1/lectures': [] })
  render(<App />)
  await waitFor(() => expect(readWorkspace()).toEqual({ courseId: 'c1', lectureId: '' }))
  expect(vi.mocked(api).mock.calls.some(([path]) => path === '/lectures/deleted')).toBe(false)
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})


function noteWorkspace() {
  saveWorkspace({ courseId: 'c1', lectureId: 'l1' })
  const note: Note = { id: 'n1', transcript_id: 't1', provider: 'extractive', model: 'local', content: { title: '主题', sections: [{ heading: '概念', items: [{ kind: 'course_content', text: '第一版正文', source_segment_ids: ['s1'] }] }] }, text_edits: {}, user_markdown: null, edit_version: 0, created_at: new Date().toISOString() }
  const detail: Detail = { id: 'l1', title: '测试课堂', duration: 30, is_demo: false, active_transcript_id: 't1', created_at: new Date().toISOString(), transcript: { id: 't1', parent_id: null, engine: 'demo', model: 'demo', created_at: '', metrics: {}, segments: [{ id: 's1', start_ms: 0, end_ms: 1000, text: '原文', raw_text: '原文' }] }, transcript_versions: [], notes: [note], jobs: [], bookmarks: [] }
  return { note, detail }
}

it('重新整理创建新任务，完成后自动显示新版本并保留旧笔记', async () => {
  const { note, detail } = noteWorkspace()
  const job = { id: 'j2', state: 'queued', kind: 'notes', stage: 'queued', error: null, created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
  let latest: Detail = detail
  let submitted: { force?: boolean } = {}
  mockRoutes({
    '/courses': [{ id: 'c1', name: '第一门课' }], '/courses/c1/lectures': [detail],
    '/lectures/l1': () => latest,
    '/lectures/l1/notes': (options: RequestInit) => { submitted = JSON.parse(options.body as string); latest = { ...detail, jobs: [job] }; return job },
  })
  render(<App />)
  expect(await screen.findByText('第一版正文')).toBeInTheDocument()
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重新整理' })) })
  expect(submitted.force).toBe(true)
  const newNote = { ...note, id: 'n2', content: { ...note.content, sections: [{ ...note.content.sections[0], items: [{ ...note.content.sections[0].items[0], text: '第二版正文' }] }] } }
  latest = { ...detail, notes: [newNote, note], jobs: [{ ...job, state: 'succeeded', result_id: 'n2' }] }
  await act(async () => { vi.advanceTimersByTime(2000) })
  expect(screen.getByText('第二版正文')).toBeInTheDocument()
  expect(screen.getByLabelText('笔记版本')).toHaveValue('n2')
  expect(screen.getByLabelText('笔记版本').querySelectorAll('option')).toHaveLength(2)
})

it('正文修改尚未保存时禁止重新整理，避免切换结果丢失草稿', async () => {
  const { detail } = noteWorkspace()
  mockRoutes({ '/courses': [{ id: 'c1', name: '第一门课' }], '/courses/c1/lectures': [detail], '/lectures/l1': detail })
  render(<App />)
  await screen.findByText('第一版正文')
  fireEvent.click(screen.getByLabelText('修改笔记 1.1'))
  fireEvent.change(screen.getByLabelText('笔记正文 1.1'), { target: { value: '未保存的修订' } })
  expect(screen.getByRole('button', { name: '重新整理' })).toBeDisabled()
  expect(screen.getByLabelText('笔记正文 1.1')).toHaveValue('未保存的修订')
})
