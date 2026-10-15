import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TranscriptPane from './TranscriptPane'
import { noteIsStale, timeLabel } from './api'

describe('转录核对与回听', () => {
  it('点击时间引用传递真实片段范围，修订只改变文字', () => {
    const segment = { id: 's1', start_ms: 61000, end_ms: 64000, text: '识别内容', raw_text: '识别内容' }
    const seek = vi.fn(), edit = vi.fn(), save = vi.fn()
    render(<TranscriptPane segments={[segment]} current={0} dirty={{ s1: '已修订' }} onSeek={seek} onEdit={edit} onSave={save} onDiscard={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('回听 01:01'))
    expect(seek).toHaveBeenCalledWith(segment)
    fireEvent.click(screen.getByLabelText('修改片段 s1'))
    fireEvent.change(screen.getByLabelText('片段文字 s1'), { target: { value: '新的术语' } })
    expect(edit).toHaveBeenCalledWith('s1', '新的术语')
    fireEvent.click(screen.getByText('保存为新版本'))
    expect(save).toHaveBeenCalledOnce()
  })
  it('根据版本识别过期笔记，保留小时以上的时间', () => {
    expect(noteIsStale('old', 'new')).toBe(true)
    expect(noteIsStale('same', 'same')).toBe(false)
    expect(timeLabel(3_661_000)).toBe('61:01')
  })
  it('旧版引用原文只读，但仍可回听', () => {
    render(<TranscriptPane readOnly segments={[{ id: 'old', start_ms: 0, end_ms: 1000, text: '旧原文', raw_text: '旧原文' }]} current={0} dirty={{}} onSeek={vi.fn()} onEdit={vi.fn()} onSave={vi.fn()} onDiscard={vi.fn()} />)
    expect(screen.queryByLabelText('修改片段 old')).not.toBeInTheDocument()
    expect(screen.getByLabelText('回听 00:00')).toBeEnabled()
  })
})
