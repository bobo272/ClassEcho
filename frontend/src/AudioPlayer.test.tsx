import { createRef } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import AudioPlayer from './AudioPlayer'

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

function player() {
  const audioRef = createRef<HTMLAudioElement>()
  const callbacks = { onTimeUpdate: vi.fn(), onSeeking: vi.fn(), onManualSeek: vi.fn(), onClose: vi.fn(), onError: vi.fn() }
  const props = { audioRef, src: '/test-audio.wav', title: '测试录音', duration: 120, position: 0, hidden: false, ...callbacks }
  const view = render(<AudioPlayer {...props} />)
  return { ...view, ...callbacks, props, media: audioRef.current! }
}

it('播放按钮和外部引用播放都随媒体事件更新，结束后可再次播放', async () => {
  const { media } = player()
  fireEvent.click(screen.getByRole('button', { name: '播放录音' }))
  await waitFor(() => expect(media.play).toHaveBeenCalledOnce())
  fireEvent.play(media)
  Object.defineProperty(media, 'paused', { configurable: true, value: false })
  fireEvent.click(screen.getByRole('button', { name: '暂停录音' }))
  expect(media.pause).toHaveBeenCalledOnce()
  fireEvent.pause(media)
  expect(screen.getByRole('button', { name: '播放录音' })).toBeInTheDocument()
  fireEvent.play(media)
  fireEvent.ended(media)
  expect(screen.getByRole('button', { name: '播放录音' })).toBeInTheDocument()
})

it('拖动进度会通知引用范围退出，并定位到指定秒数', () => {
  const { media, onManualSeek, onTimeUpdate } = player()
  fireEvent.change(screen.getByRole('slider', { name: '播放进度' }), { target: { value: '45.5' } })
  expect(onManualSeek).toHaveBeenCalledWith(45.5)
  expect(media.currentTime).toBe(45.5)
  fireEvent.timeUpdate(media)
  expect(onTimeUpdate).toHaveBeenCalledOnce()
})

it('静音恢复原音量，零音量也可以解除静音，倍速修改媒体属性', () => {
  const { media } = player()
  fireEvent.change(screen.getByRole('slider', { name: '音量' }), { target: { value: '0.4' } })
  expect(media.volume).toBe(0.4)
  fireEvent.click(screen.getByRole('button', { name: '静音' }))
  expect(media.muted).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '取消静音' }))
  expect(media.muted).toBe(false)
  expect(media.volume).toBe(0.4)
  fireEvent.change(screen.getByRole('slider', { name: '音量' }), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('button', { name: '取消静音' }))
  expect(media.volume).toBe(1)
  fireEvent.change(screen.getByRole('combobox', { name: '播放速度' }), { target: { value: '1.5' } })
  expect(media.playbackRate).toBe(1.5)
})

it('加载后采用实际媒体时长，并忽略无效时长', () => {
  const { media } = player()
  expect(screen.getByRole('slider', { name: '播放进度' })).toHaveAttribute('max', '120')
  Object.defineProperty(media, 'duration', { configurable: true, value: 125.5 })
  fireEvent.loadedMetadata(media)
  expect(screen.getByRole('slider', { name: '播放进度' })).toHaveAttribute('max', '125.5')
  Object.defineProperty(media, 'duration', { configurable: true, value: Infinity })
  fireEvent.durationChange(media)
  expect(screen.getByRole('slider', { name: '播放进度' })).toHaveAttribute('max', '120')
})

it('播放被浏览器拒绝时反馈错误，不伪装成播放中', async () => {
  const { media, onError } = player()
  vi.mocked(media.play).mockRejectedValueOnce(new Error('NotAllowedError'))
  fireEvent.click(screen.getByRole('button', { name: '播放录音' }))
  await waitFor(() => expect(onError).toHaveBeenCalledWith('播放失败，请检查媒体文件后重试'))
  expect(screen.getByRole('button', { name: '播放录音' })).toBeInTheDocument()
})

it('收起面板时保留媒体节点，引用可直接设置定位和播放', () => {
  const { media, props, rerender, container } = player()
  media.currentTime = 10
  rerender(<AudioPlayer {...props} hidden />)
  expect(screen.getByLabelText('录音播放器')).not.toBeVisible()
  expect(container.querySelector('audio')).toBe(media)
  expect(media.currentTime).toBe(10)
  expect(media.controls).toBe(false)
})
