import { afterEach, expect, it, vi } from 'vitest'
import { LiveTranscription } from './liveTranscription'
import { api } from './api'

vi.mock('./api', () => ({ api: vi.fn() }))
afterEach(() => { vi.mocked(api).mockReset() })

it('后台识别慢时最多保留一个待发送窗口，不无限堆积请求', async () => {
  let resolve: (value: unknown) => void = () => {}
  vi.mocked(api).mockReturnValueOnce(new Promise(done => { resolve = done }))
  vi.mocked(api).mockResolvedValue({ id: 'next', state: 'succeeded', segments: [], error: null })
  const text = vi.fn(), status = vi.fn()
  const live = new LiveTranscription(text, status)
  for (let second = 0; second < 35; second++) live.accept(new Int16Array(16000))
  expect(api).toHaveBeenCalledOnce()
  resolve({ id: 'first', state: 'succeeded', segments: [{ id: 's1', text: '文字' }], error: null })
  await new Promise(done => setTimeout(done, 0))
  expect(api).toHaveBeenCalledTimes(2)
  const form = vi.mocked(api).mock.calls[1][1]!.body as FormData
  expect(form.get('offset_ms')).toBe('25000')
  expect(text).toHaveBeenCalledOnce()
  live.dispose()
})

it('结束录音后丢弃到达的预览，不更新已关闭界面', async () => {
  let resolve: (value: unknown) => void = () => {}
  vi.mocked(api).mockReturnValueOnce(new Promise(done => { resolve = done }))
  const text = vi.fn(), status = vi.fn(), live = new LiveTranscription(text, status)
  live.accept(new Int16Array(160000)); live.dispose(); status.mockClear()
  resolve({ id: 'preview', state: 'succeeded', segments: [{ text: '迟到结果' }], error: null })
  await new Promise(done => setTimeout(done, 0))
  expect(text).not.toHaveBeenCalled(); expect(status).not.toHaveBeenCalled()
})
