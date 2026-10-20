import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import MicrophoneRecorder from './MicrophoneRecorder'
import { recordingFile } from './microphone'

class FakeRecorder {
  static isTypeSupported = () => true
  static instance: FakeRecorder
  state = 'inactive'; mimeType = 'audio/webm;codecs=opus'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  start = vi.fn(() => { this.state = 'recording' })
  pause = vi.fn(() => { this.state = 'paused' })
  resume = vi.fn(() => { this.state = 'recording' })
  stop = vi.fn(() => { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['audio']) }); this.onstop?.() })
  constructor() { FakeRecorder.instance = this }
}
let track: { stop: ReturnType<typeof vi.fn>; onended: (() => void) | null }
let input: MediaStream
const getUserMedia = vi.fn()
beforeEach(() => {
  track = { stop: vi.fn(), onended: null }
  input = { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream
  getUserMedia.mockReset().mockResolvedValue(input)
  vi.stubGlobal('MediaRecorder', FakeRecorder)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  vi.stubGlobal('confirm', vi.fn(() => false))
  URL.createObjectURL = vi.fn(() => 'blob:recording'); URL.revokeObjectURL = vi.fn()
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('录音、暂停、继续、停止及保存；先停止麦克风再保留预览', async () => {
  const save = vi.fn().mockResolvedValue(undefined)
  render(<MicrophoneRecorder courseName="测试课" onClose={vi.fn()} onSave={save} />)
  fireEvent.click(screen.getByRole('checkbox', { name: '结束后自动整理笔记' }))
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  await screen.findByRole('button', { name: '暂停录音' })
  expect(getUserMedia).toHaveBeenCalledWith(expect.objectContaining({ video: false }))
  fireEvent.click(screen.getByRole('button', { name: '暂停录音' }))
  expect(FakeRecorder.instance.state).toBe('paused')
  fireEvent.click(screen.getByRole('button', { name: '继续录音' }))
  expect(FakeRecorder.instance.state).toBe('recording')
  fireEvent.click(screen.getByRole('button', { name: '结束录音' }))
  expect(track.stop).toHaveBeenCalled()
  expect(screen.getByLabelText('本次录音预览')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '保存录音' }))
  await waitFor(() => expect(save).toHaveBeenCalledOnce())
  expect(save.mock.calls[0][0].name).toMatch(/\.webm$/)
})

it('拒绝麦克风权限后允许重试，不产生录音', async () => {
  getUserMedia.mockRejectedValueOnce(new DOMException('denied', 'NotAllowedError'))
  render(<MicrophoneRecorder courseName="测试课" onClose={vi.fn()} onSave={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('麦克风权限未获允许')
  expect(screen.getByRole('button', { name: '开始录音' })).toBeEnabled()
})

it('权限请求期间关闭，随后到达的媒体流也会被释放', async () => {
  let resolve: (value: MediaStream) => void = () => {}
  getUserMedia.mockReturnValueOnce(new Promise<MediaStream>(done => { resolve = done }))
  const view = render(<MicrophoneRecorder courseName="测试课" onClose={vi.fn()} onSave={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  view.unmount()
  await act(async () => { resolve(input) })
  expect(track.stop).toHaveBeenCalledOnce()
})

it('上传失败保留录音和下载入口；取消关闭不丢失录音', async () => {
  const close = vi.fn(), save = vi.fn().mockRejectedValue(new Error('网络中断'))
  render(<MicrophoneRecorder courseName="测试课" onClose={close} onSave={save} />)
  fireEvent.click(screen.getByRole('checkbox', { name: '结束后自动整理笔记' }))
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  await screen.findByRole('button', { name: '结束录音' })
  fireEvent.click(screen.getByRole('button', { name: '结束录音' }))
  fireEvent.click(screen.getByRole('button', { name: '保存录音' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('网络中断')
  expect(screen.getByRole('link', { name: '下载录音' })).toHaveAttribute('href', 'blob:recording')
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(close).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '保存录音' })).toBeEnabled()
})

it('Safari MP4 使用 m4a 后缀，文件名去除路径字符', () => {
  expect(recordingFile(new Blob(['audio'], { type: 'audio/mp4' }), '../课堂/录音').name).toBe('.._课堂_录音.m4a')
})

it('结束录音后自动保存并携带整理选项，失败后可以重试且保留音频', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('队列暂不可用')).mockResolvedValue(undefined)
  render(<MicrophoneRecorder courseName="测试课" onClose={vi.fn()} onSave={save} />)
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  await screen.findByRole('button', { name: '结束录音' })
  fireEvent.click(screen.getByRole('button', { name: '结束录音' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('队列暂不可用')
  expect(save.mock.calls[0][1]).toEqual({ provider: 'extractive', consent: false, api_revision: '' })
  expect(screen.getByRole('link', { name: '下载录音' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '重试保存并整理' }))
  expect(await screen.findByRole('button', { name: '已保存' })).toBeDisabled()
  expect(save).toHaveBeenCalledTimes(2)
})

it('AI 整理必须确认具体地址，录音开始后冻结目的地址与配置版本', async () => {
  const config = { base_url: 'https://relay.example.invalid/v1', model: 'test-model', configured: true, key_configured: true, revision: 'revision-1' }
  const save = vi.fn().mockResolvedValue(undefined)
  render(<MicrophoneRecorder courseName="测试课" notesAPI={config} onClose={vi.fn()} onSave={save} />)
  expect(screen.getByRole('button', { name: '开始录音' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox', { name: /结束后将转录文字发送至/ }))
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  await screen.findByRole('button', { name: '结束录音' })
  expect(screen.getByRole('combobox', { name: '录音后的笔记方式' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '结束录音' }))
  await waitFor(() => expect(save).toHaveBeenCalledOnce())
  expect(save.mock.calls[0][1]).toEqual({ provider: 'api', consent: true, api_revision: 'revision-1' })
})

it('浏览器自行结束录音也会释放麦克风并保留已有音频', async () => {
  render(<MicrophoneRecorder courseName="测试课" onClose={vi.fn()} onSave={vi.fn()} />)
  fireEvent.click(screen.getByRole('checkbox', { name: '结束后自动整理笔记' }))
  fireEvent.click(screen.getByRole('button', { name: '开始录音' }))
  await screen.findByRole('button', { name: '结束录音' })
  act(() => { FakeRecorder.instance.stop() })
  expect(track.stop).toHaveBeenCalled()
  expect(screen.getByLabelText('本次录音预览')).toBeInTheDocument()
})
