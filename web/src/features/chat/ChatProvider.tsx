import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { api } from '../../api/endpoints'
import { useSettings } from '../../state/useSettings'
import { ChatContext, type ChatContextValue, type ChatTurn } from './useChat'

/** Owns the conversation at app level so it survives navigating between pages. */
export function ChatProvider({ children }: { children: ReactNode }) {
  const { params } = useSettings()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [busy, setBusy] = useState(false)
  const session = useRef<string | null>(null)
  const abort = useRef<AbortController | null>(null)
  const nextId = useRef(0)

  const patchTurn = useCallback((id: number, patch: (t: ChatTurn) => Partial<ChatTurn>) => {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)))
  }, [])

  const send = useCallback(
    async (text: string) => {
      const question = text.trim()
      if (!question || busy) return
      const userTurn: ChatTurn = { id: nextId.current++, role: 'user', text: question, tools: [], status: 'done' }
      const reply: ChatTurn = { id: nextId.current++, role: 'assistant', text: '', tools: [], status: 'pending' }
      setTurns((all) => [...all, userTurn, reply])
      setBusy(true)
      abort.current = new AbortController()

      const ask = async (retry: boolean): Promise<void> => {
        session.current ??= (await api.createChat(params)).id
        try {
          await api.sendChat(
            session.current,
            question,
            (e) => {
              if (e.event === 'tool') patchTurn(reply.id, (t) => ({ tools: [...t.tools, e.data.label] }))
              else if (e.event === 'answer') patchTurn(reply.id, () => ({ text: e.data.text, status: 'done' }))
              else patchTurn(reply.id, () => ({ text: e.data.message, status: 'error' }))
            },
            abort.current?.signal,
          )
        } catch (err) {
          if (retry && err instanceof ApiError && err.status === 404) {
            session.current = null // server restarted or evicted the session: start a fresh one
            return ask(false)
          }
          throw err
        }
      }

      try {
        await ask(true)
      } catch (err) {
        const aborted = err instanceof DOMException && err.name === 'AbortError'
        patchTurn(reply.id, () => ({
          text: aborted ? 'Stopped.' : err instanceof Error ? err.message : 'Something went wrong.',
          status: aborted ? 'done' : 'error',
        }))
      } finally {
        setBusy(false)
        abort.current = null
      }
    },
    [busy, params, patchTurn],
  )

  const stop = useCallback(() => abort.current?.abort(), [])

  const reset = useCallback(() => {
    abort.current?.abort()
    if (session.current) void api.deleteChat(session.current).catch(() => undefined)
    session.current = null
    setTurns([])
  }, [])

  const value = useMemo<ChatContextValue>(() => ({ turns, busy, send, reset, stop }), [turns, busy, send, reset, stop])
  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}
