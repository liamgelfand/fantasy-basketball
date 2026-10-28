import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { api } from '../../api/endpoints'
import { SettingsProvider } from '../../state/settings'
import { ChatProvider } from './ChatProvider'
import { useChat } from './useChat'

vi.mock('../../api/endpoints', () => ({
  api: { createChat: vi.fn(), sendChat: vi.fn(), deleteChat: vi.fn() },
}))
const mocked = vi.mocked(api)

const wrapper = ({ children }: { children: ReactNode }) => (
  <SettingsProvider>
    <ChatProvider>{children}</ChatProvider>
  </SettingsProvider>
)

beforeEach(() => {
  localStorage.clear()
  vi.resetAllMocks()
  mocked.createChat.mockResolvedValue({ id: 's1' })
})

describe('ChatProvider', () => {
  it('streams tool progress then the answer, and saves the conversation', async () => {
    mocked.sendChat.mockImplementation(async (_s, _id, _text, onEvent) => {
      onEvent({ event: 'tool', data: { name: 'my_roster', label: 'my roster' } })
      onEvent({ event: 'answer', data: { text: 'Drop Player 5.' } })
    })
    const { result } = renderHook(useChat, { wrapper })

    await act(() => result.current.send('who do I drop?'))

    const [user, reply] = result.current.turns
    expect(user).toMatchObject({ role: 'user', text: 'who do I drop?' })
    expect(reply).toMatchObject({ role: 'assistant', text: 'Drop Player 5.', tools: ['my roster'], status: 'done' })
    const saved = JSON.parse(localStorage.getItem('fantasy-hq:chat')!)
    expect(saved.session).toBe('s1')
    expect(saved.turns).toHaveLength(2)
  })

  it('starts a fresh session with a notice when the server lost the old one', async () => {
    localStorage.setItem('fantasy-hq:chat', JSON.stringify({ session: 'gone', turns: [] }))
    mocked.sendChat
      .mockRejectedValueOnce(new ApiError(404, 'Chat session expired.'))
      .mockImplementationOnce(async (_s, _id, _text, onEvent) => onEvent({ event: 'answer', data: { text: 'ok' } }))
    const { result } = renderHook(useChat, { wrapper })

    await act(() => result.current.send('hello'))

    expect(mocked.sendChat).toHaveBeenLastCalledWith(expect.anything(), 's1', 'hello', expect.any(Function), expect.anything())
    expect(result.current.turns.map((t) => t.role)).toEqual(['notice', 'user', 'assistant'])
    expect(result.current.turns[2].text).toBe('ok')
  })

  it('marks a reply that was cut off by a reload as interrupted', async () => {
    localStorage.setItem(
      'fantasy-hq:chat',
      JSON.stringify({ session: 's1', turns: [{ id: 0, role: 'assistant', text: '', tools: [], status: 'pending' }] }),
    )
    const { result } = renderHook(useChat, { wrapper })
    await waitFor(() => expect(result.current.turns[0].status).toBe('error'))
    expect(result.current.busy).toBe(false)
  })
})
