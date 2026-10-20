import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import APISettings from './APISettings'
import { api } from './api'

vi.mock('./api', () => ({ api: vi.fn() }))
const config = { base_url: 'https://relay.example.invalid/v1', model: 'test-model', configured: true, key_configured: true, revision: 'v1' }
afterEach(cleanup)
beforeEach(() => { vi.mocked(api).mockReset() })

it('可以保存自定义地址、模型和密钥，成功后清空密钥输入框', async () => {
  const onSaved = vi.fn()
  vi.mocked(api).mockResolvedValue({ ...config, revision: 'v2' })
  render(<APISettings config={config} onSaved={onSaved} />)
  expect(screen.getByLabelText('API Key')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('API URL'), { target: { value: 'https://new.example.invalid/v1' } })
  fireEvent.change(screen.getByLabelText('模型名称'), { target: { value: 'another-model' } })
  fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'test-only-fake-key' } })
  fireEvent.click(screen.getByRole('button', { name: '保存接口' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(api).toHaveBeenCalledWith('/settings/notes-api', { method: 'PUT', body: JSON.stringify({ base_url: 'https://new.example.invalid/v1', model: 'another-model', api_key: 'test-only-fake-key' }) })
  expect(screen.getByLabelText('API Key')).toHaveValue('')
})

it('留空密钥不会覆盖已有密钥，保存失败保留表单并显示错误', async () => {
  vi.mocked(api).mockRejectedValue(new Error('接口设置保存失败'))
  render(<APISettings config={config} onSaved={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: '保存接口' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('接口设置保存失败')
  expect(JSON.parse(vi.mocked(api).mock.calls[0][1]!.body as string)).not.toHaveProperty('api_key')
  expect(screen.getByLabelText('API URL')).toHaveValue(config.base_url)
})
