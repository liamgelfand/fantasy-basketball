import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/client'
import { api } from '../../api/endpoints'
import type { AssistantEvent } from '../../api/types'
import { useSettings } from '../../state/useSettings'
import { ChatContext, type ChatContextValue, type ChatTurn } from './useChat'

const STORAGE_KEY = 'fantasy-hq:chat'

interface Saved {
  session: string | null
  turns: ChatTurn[]
}

function load(): Saved {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const saved = JSON.parse(raw) as Saved
      // A reply that was still streaming when the page closed will never finish.
      const turns = saved.turns.map((t) =>
        t.status === 'pending' ? { ...t, status: 'error' as const, text: t.text || 'Interrupted. Ask again.' } : t,
      )
      return { session: saved.session, turns }
    }
  } catch {
    /* storage blocked or corrupt: start empty */
  }
  return { session: null, turns: [] }
}

function save(data: Saved) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    /* non-essential */
  }
}

const isAbort = (err: unknown) => err instanceof DOMException && err.name === 'AbortError'

/**
 * Owns the conversation at app level so it survives page navigation and reloads. The server
 * keeps Claude's side of the history (on disk), keyed by the session id saved here.
 */
export function ChatProvider({ children }: { children: ReactNode }) {
  const { params } = useSettings()
  const [initial] = useState(load)
  const [turns, setTurns] = useState<ChatTurn[]>(initial.turns)
  const [busy, setBusy] = useState(false)
  const session = useRef<string | null>(initial.session)
  const abort = useRef<AbortController | null>(null)
  const nextId = useRef(initial.turns.reduce((max, t) => Math.max(max, t.id + 1), 0))

  useEffect(() => save({ session: session.current, turns }), [turns])

  const patchTurn = useCallback((id: number, patch: (t: ChatTurn) => Partial<ChatTurn>) => {
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)))
  }, [])

  const newTurn = useCallback(
    (role: ChatTurn['role'], text: string, status: ChatTurn['status'] = 'done'): ChatTurn => ({
      id: nextId.current++,
      role,
      text,
      tools: [],
      status,
    }),
    [],
  )

  const send = useCallback(
    async (text: string) => {
      const question = text.trim()
      if (!question || busy) return
      const reply = newTurn('assistant', '', 'pending')
      setTurns((all) => [...all, newTurn('user', question), reply])
      setBusy(true)
      const controller = new AbortController()
      abort.current = controller

      const onEvent = (e: AssistantEvent) => {
        if (e.event === 'tool') patchTurn(reply.id, (t) => ({ tools: [...t.tools, e.data.label] }))
        else if (e.event === 'answer') patchTurn(reply.id, () => ({ text: e.data.text, status: 'done' }))
        else patchTurn(reply.id, () => ({ text: e.data.message, status: 'error' }))
      }

      const ask = async (retry: boolean): Promise<void> => {
        // Saved with the turns by the effect above as the reply streams in.
        session.current ??= (await api.createChat(params)).id
        try {
          await api.sendChat(params, session.current, question, onEvent, controller.signal)
        } catch (err) {
          if (retry && err instanceof ApiError && err.status === 404) {
            // The server no longer has this conversation: continue in a fresh one, and say so.
            session.current = null
            setTurns((all) => {
              const i = all.findIndex((t) => t.id === reply.id)
              const notice = newTurn('notice', "Claude's memory of the earlier messages was lost. Starting fresh.")
              return [...all.slice(0, i - 1), notice, ...all.slice(i - 1)]
            })
            return ask(false)
          }
          throw err
        }
      }

      try {
        await ask(true)
      } catch (err) {
        patchTurn(reply.id, (t) =>
          isAbort(err)
            ? { text: t.text || 'Stopped.', status: 'done' }
            : { text: err instanceof Error ? err.message : 'Something went wrong.', status: 'error' },
        )
      } finally {
        setBusy(false)
        abort.current = null
      }
    },
    [busy, params, patchTurn, newTurn],
  )

  // Closing the stream makes the server cancel Claude's work before its next API call.
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
