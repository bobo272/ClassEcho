export const PCM_RATE = 16000

// Weighted averaging keeps the sample clock continuous across AudioWorklet render blocks.
export class PcmResampler {
  private sum = 0
  private filled = 0
  private ratio: number
  constructor(inputRate: number) { this.ratio = inputRate / PCM_RATE }
  push(input: Float32Array) {
    const output: number[] = []
    for (const raw of input) {
      let remaining = 1
      const value = Math.max(-1, Math.min(1, raw))
      while (remaining > 1e-8) {
        const part = Math.min(remaining, this.ratio - this.filled)
        this.sum += value * part; this.filled += part; remaining -= part
        if (this.filled >= this.ratio - 1e-8) {
          const averaged = this.sum / this.ratio
          output.push(Math.round(averaged * (averaged < 0 ? 32768 : 32767)))
          this.sum = 0; this.filled = 0
        }
      }
    }
    return new Int16Array(output)
  }
}

export function wavBlob(samples: Int16Array) {
  const bytes = new ArrayBuffer(44 + samples.length * 2), view = new DataView(bytes)
  const text = (offset: number, value: string) => { [...value].forEach((letter, index) => view.setUint8(offset + index, letter.charCodeAt(0))) }
  text(0, 'RIFF'); view.setUint32(4, 36 + samples.length * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, PCM_RATE, true); view.setUint32(28, PCM_RATE * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  text(36, 'data'); view.setUint32(40, samples.length * 2, true)
  samples.forEach((sample, index) => view.setInt16(44 + index * 2, sample, true))
  return new Blob([bytes], { type: 'audio/wav' })
}
