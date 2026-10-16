import { useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import Dialog from './Dialog'

afterEach(cleanup)

function Harness() {
  const [open, setOpen] = useState(false)
  return <><button onClick={() => setOpen(true)}>打开设置</button>{open && <Dialog title="测试设置" closeLabel="关闭测试设置" onClose={() => setOpen(false)}><label>接口地址<input /></label><button>保存设置</button></Dialog>}</>
}

it('弹窗有可访问名称、聚焦输入区，Tab 不离开弹窗', () => {
  render(<Harness />)
  fireEvent.click(screen.getByRole('button', { name: '打开设置' }))
  expect(screen.getByRole('dialog', { name: '测试设置' })).toHaveAttribute('aria-modal', 'true')
  expect(screen.getByLabelText('接口地址')).toHaveFocus()
  screen.getByRole('button', { name: '保存设置' }).focus()
  fireEvent.keyDown(document, { key: 'Tab' })
  expect(screen.getByRole('button', { name: '关闭测试设置' })).toHaveFocus()
  fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
  expect(screen.getByRole('button', { name: '保存设置' })).toHaveFocus()
})

it('Escape 关闭后恢复触发按钮焦点和页面滚动', () => {
  render(<Harness />)
  const trigger = screen.getByRole('button', { name: '打开设置' })
  trigger.focus()
  const overflow = document.body.style.overflow
  fireEvent.click(trigger)
  expect(document.body.style.overflow).toBe('hidden')
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
  expect(document.body.style.overflow).toBe(overflow)
})
