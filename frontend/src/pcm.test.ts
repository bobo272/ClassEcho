import { expect, it } from 'vitest'
import { PcmResampler, wavBlob } from './pcm'

it('48k 和 44.1k 输入分块处理后维持 16k 时间轴，限制 PCM 振幅', () => {
  for (const rate of [48000, 44100, 16000]) {
    const converter = new PcmResampler(rate)
    const audio = new Float32Array(rate).fill(2)
    const result = []
    for (let start = 0; start < rate; start += 128) result.push(...converter.push(audio.slice(start, start + 128)))
    expect(result).toHaveLength(16000)
    expect(result.every(value => value === 32767)).toBe(true)
  }
  expect(new PcmResampler(16000).push(new Float32Array([-2, 0, 1]))).toEqual(new Int16Array([-32768, 0, 32767]))
})

it('WAV 包含可独立解码的文件头和小端 PCM16 数据', async () => {
  const result = wavBlob(new Int16Array([-32768, 0, 32767]))
  const bytes = await new Promise<ArrayBuffer>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result as ArrayBuffer); reader.readAsArrayBuffer(result) })
  const view = new DataView(bytes)
  expect(result.type).toBe('audio/wav')
  expect(view.byteLength).toBe(50)
  expect(view.getUint32(24, true)).toBe(16000)
  expect(view.getUint32(40, true)).toBe(6)
  expect(view.getInt16(44, true)).toBe(-32768)
  expect(view.getInt16(48, true)).toBe(32767)
})
