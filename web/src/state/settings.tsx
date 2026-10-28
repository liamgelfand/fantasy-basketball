import { useCallback, useMemo, useState, type ReactNode } from 'react'
import type { SnapshotParams } from '../api/client'
import { SettingsContext, type SettingsContextValue } from './useSettings'

const STORAGE_KEY = 'fantasy-hq:settings'

function load(): SnapshotParams {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SnapshotParams>
      return { window: parsed.window ?? null, punts: parsed.punts ?? null }
    }
  } catch {
    /* storage blocked or corrupt: fall back to server defaults */
  }
  return { window: null, punts: null }
}

function save(params: SnapshotParams) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(params))
  } catch {
    /* non-essential */
  }
}

/** Stat window and punts, remembered per browser. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useState<SnapshotParams>(load)

  const update = useCallback((patch: Partial<SnapshotParams>) => {
    setParams((prev) => {
      const next = { ...prev, ...patch }
      save(next)
      return next
    })
  }, [])

  const value = useMemo<SettingsContextValue>(
    () => ({
      params,
      setWindow: (window) => update({ window }),
      setPunts: (punts) => update({ punts: [...punts].sort() }),
    }),
    [params, update],
  )
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}
