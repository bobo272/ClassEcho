import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api'
import { saveWorkspace } from './workspace'

vi.mock('./api', async original => ({ ...await original<typeof import('./api')>(), api: vi.fn() }))
afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('结束录音后提交后台处理；提交失败保留音频，重试不重复创建录音', async () => {
  const track = { stop: vi.fn() }
  class Recorder {
    static isTypeSupported = () => true
    state = 'inactive'; mimeType = 'audio/webm'
    onstop = () => {}; ondataavailable = (_event: { data: Blob }) => {}
    start() { this.state = 'recording' }
    stop() { this.state = 'inactive'; this.ondataavailable({ data: new Blob(['recording']) }); this.onstop() }
  }
  vi.stubGlobal('MediaRecorder', Recorder)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track], getAudioTracks: () => [track] }) } })
  URL.createObjectURL = vi.fn(() => 'blob:recording'); URL.revokeObjectURL = vi.fn()
  saveWorkspace({ courseId: 'c1', lectureId: '' })
  const lecture = { id: 'l1', title: '录音工作流', duration: 30, is_demo: false, active_transcript_id: null, created_at: new Date().toISOString() }
  const settings = { models: [{ name: 'small', ready: false }], notes_api: { base_url: '', model: '', configured: false, key_configured: false, revision: '' } }
  let submitted = 0
  vi.mocked(api).mockImplementation(async <T,>(path: string, options?: RequestInit): Promise<T> => {
    if (path === '/courses') return [{ id: 'c1', name: '测试课' }] as T
    if (path === '/settings') return settings as T
    if (path === '/courses/c1/lectures') return (options?.method === 'POST' ? lecture : []) as T
    if (path === '/lectures/l1/transcribe') {
      submitted++
      expect(JSON.parse(options!.body as string)).toEqual({ model: 'small', after_transcribe: { provider: 'extractive', consent: false, api_revision: '' } })
      if (submitted === 1) throw new Error('任务提交暂不可用')
      return { id: 'j1' } as T
    }
    if (path === '/lectures/l1') return { ...lecture, notes: [], transcript: null, transcript_versions: [], jobs: [], bookmarks: [] } as T
    throw new Error(`Unexpected API path: ${path}`)
  })
  render(<App />)
  await waitFor(() => expect(screen.getByRole('button', { name: '麦克风录音' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: '麦克风录音' }))
  fireEvent.click(await screen.findByRole('button', { name: '开始录音' }))
  fireEvent.click(await screen.findByRole('button', { name: '结束录音' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('任务提交暂不可用')
  expect(screen.getByLabelText('本次录音预览')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重试保存并整理' }))
  expect(await screen.findByRole('heading', { name: '录音工作流' })).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  const uploads = vi.mocked(api).mock.calls.filter(([path, options]) => path === '/courses/c1/lectures' && options?.method === 'POST')
  expect(uploads).toHaveLength(1)
  expect(submitted).toBe(2)
  expect(track.stop).toHaveBeenCalled()
})
