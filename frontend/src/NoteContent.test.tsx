import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import NoteContent from './NoteContent'
import type { Note } from './types'

afterEach(cleanup)
const segment = { id: 's1', start_ms: 61000, end_ms: 64000, text: '原文证据', raw_text: '原文证据' }
const note: Note = { id: 'n1', transcript_id: 't1', provider: 'api', model: 'test-model', content: { title: '主题', sections: [{ heading: '概念', items: [{ kind: 'course_content', text: '生成的笔记', source_segment_ids: ['s1'] }] }] }, text_edits: {}, user_markdown: null, edit_version: 0, created_at: '' }

it('编辑正文只提交文字，仍通过原片段回听', () => {
  const onEdit = vi.fn(), onSeek = vi.fn()
  render(<NoteContent note={note} segments={[segment]} drafts={{}} busy={false} onEdit={onEdit} onSave={vi.fn()} onDiscard={vi.fn()} onSeek={onSeek} />)
  fireEvent.click(screen.getByLabelText('修改笔记 1.1'))
  fireEvent.change(screen.getByLabelText('笔记正文 1.1'), { target: { value: '核对后的正文' } })
  expect(onEdit).toHaveBeenCalledWith('0.0', '核对后的正文')
  fireEvent.click(screen.getByRole('button', { name: /01:01/ }))
  expect(onSeek).toHaveBeenCalledWith(segment)
})

it('显示用户修订并保留原文，可以恢复和保存', () => {
  const onEdit = vi.fn(), onSave = vi.fn()
  render(<NoteContent note={note} segments={[segment]} drafts={{ '0.0': '核对后的正文' }} busy={false} onEdit={onEdit} onSave={onSave} onDiscard={vi.fn()} onSeek={vi.fn()} />)
  expect(screen.getByText('核对后的正文')).toBeInTheDocument()
  expect(screen.getByText('生成的笔记')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('恢复原始笔记 1.1'))
  expect(onEdit).toHaveBeenCalledWith('0.0', '生成的笔记')
  fireEvent.click(screen.getByRole('button', { name: '保存正文' }))
  expect(onSave).toHaveBeenCalledOnce()
})

it('空白正文不能保存，放弃操作不会改写原始笔记', () => {
  const onDiscard = vi.fn()
  render(<NoteContent note={note} segments={[]} drafts={{ '0.0': '  ' }} busy={false} onEdit={vi.fn()} onSave={vi.fn()} onDiscard={onDiscard} onSeek={vi.fn()} />)
  expect(screen.getByRole('button', { name: '保存正文' })).toBeDisabled()
  fireEvent.click(screen.getByLabelText('放弃正文修改'))
  expect(onDiscard).toHaveBeenCalledOnce()
  expect(note.content.sections[0].items[0].text).toBe('生成的笔记')
})
