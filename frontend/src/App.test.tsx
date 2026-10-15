import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api', async importOriginal => {
  const original = await importOriginal<typeof import('./api')>()
  return { ...original, api: vi.fn(async (path: string) => {
    if (path === '/courses') return []
    if (path === '/settings') return { models: [{ name: 'small', ready: true }] }
    throw new Error(`Unexpected API path: ${path}`)
  }) }
})

it('设置保留本地模型状态，移除云端笔记与预算面板', async () => {
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: '设置' }))
  expect(await screen.findByText('模型已就绪')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '本地转录' })).toBeInTheDocument()
  expect(screen.queryByText('云端笔记')).not.toBeInTheDocument()
  expect(screen.queryByText(/预算 ¥/)).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /查看逐次用量记录/ })).not.toBeInTheDocument()
})
