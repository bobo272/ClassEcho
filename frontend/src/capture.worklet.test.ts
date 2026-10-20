import { expect, it, vi } from 'vitest'

it('真实采音处理器按 16k 发送分片，暂停期间不采集并保留暂停前尾部', async () => {
  const postMessage = vi.fn()
  class Processor {
    port = { onmessage: null as ((event: { data: { paused: boolean } }) => void) | null, postMessage }
  }
  let constructor: (new () => Processor & { process: (inputs: Float32Array[][]) => boolean }) | null = null
  vi.stubGlobal('AudioWorkletProcessor', Processor)
  vi.stubGlobal('sampleRate', 48000)
  vi.stubGlobal('registerProcessor', (_name: string, value: typeof constructor) => { constructor = value })
  try {
    await import('./capture.worklet')
    const Capture = constructor! as new () => Processor & { process: (inputs: Float32Array[][]) => boolean }
    const capture = new Capture()
    capture.process([[new Float32Array(48000)]])
    expect(postMessage).not.toHaveBeenCalled()
    capture.port.onmessage!({ data: { paused: false } })
    capture.process([[new Float32Array(48000)]])
    expect(postMessage.mock.calls[0][0]).toHaveLength(16000)
    capture.process([[new Float32Array(4800)]])
    capture.port.onmessage!({ data: { paused: true } })
    expect(postMessage.mock.calls[1][0]).toHaveLength(1600)
    capture.process([[new Float32Array(48000)]])
    expect(postMessage).toHaveBeenCalledTimes(2)
  } finally { vi.unstubAllGlobals() }
})
