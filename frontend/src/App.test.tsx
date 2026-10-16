import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'
import { readWorkspace, saveWorkspace } from './workspace'

vi.mock('./api', async importOriginal => {
  const original = await importOriginal<typeof import('./api')>()
  return { ...original, api: vi.fn() }
})
const settings = { models: [{ name: 'small', ready: true }], notes_api: { base_url: '', model: '', configured: false, key_configured: false, revision: '' } }
function mockRoutes(extra: Record<string, unknown> = {}) {
  const routes = { '/courses': [], '/settings': settings, ...extra }
  vi.mocked(api).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (!(path in routes)) throw new Error(`Unexpected API path: ${path}`)
    return routes[path as keyof typeof routes] as T
  })
}
beforeEach(() => { localStorage.clear(); vi.mocked(api).mockReset(); mockRoutes() })
afterEach(cleanup)

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
