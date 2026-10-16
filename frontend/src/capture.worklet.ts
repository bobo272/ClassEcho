import { PCM_RATE, PcmResampler } from './pcm'

declare const sampleRate: number
declare function registerProcessor(name: string, processor: typeof AudioWorkletProcessor): void
declare abstract class AudioWorkletProcessor {
  readonly port: MessagePort
  abstract process(inputs: Float32Array[][]): boolean
}

class MicrophoneProcessor extends AudioWorkletProcessor {
  private resampler = new PcmResampler(sampleRate)
  private enabled = false
  private buffer = new Int16Array(PCM_RATE)
  private cursor = 0
  constructor() {
    super()
    this.port.onmessage = event => {
      this.enabled = !event.data.paused
      // Flush before pausing so the preview's sample clock matches the recording.
      if (!this.enabled && this.cursor) {
        const part = this.buffer.slice(0, this.cursor)
        this.port.postMessage(part, [part.buffer]); this.cursor = 0
      }
    }
  }
  process(inputs: Float32Array[][]) {
    if (!this.enabled || !inputs[0]?.[0]) return true
    const samples = this.resampler.push(inputs[0][0])
    for (const sample of samples) {
      this.buffer[this.cursor++] = sample
      if (this.cursor === this.buffer.length) {
        this.port.postMessage(this.buffer, [this.buffer.buffer])
        this.buffer = new Int16Array(PCM_RATE); this.cursor = 0
      }
    }
    return true
  }
}
registerProcessor('classecho-microphone', MicrophoneProcessor)
