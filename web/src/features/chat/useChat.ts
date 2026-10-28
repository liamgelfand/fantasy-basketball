import { createContext, useContext } from 'react'

export interface ChatTurn {
  id: number
  /** `notice` is an app message in the thread (e.g. "context was reset"), not from either party. */
  role: 'user' | 'assistant' | 'notice'
  text: string
  tools: string[]
  status: 'pending' | 'done' | 'error'
}

export interface ChatContextValue {
  turns: ChatTurn[]
  busy: boolean
  send: (text: string) => Promise<void>
  reset: () => void
  stop: () => void
}

export const ChatContext = createContext<ChatContextValue | null>(null)

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChat must be used inside <ChatProvider>')
  return ctx
}
