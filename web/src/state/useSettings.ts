import { createContext, useContext } from 'react'
import type { SnapshotParams } from '../api/client'

export interface SettingsContextValue {
  /** null fields mean "use the server's .env default". */
  params: SnapshotParams
  setWindow: (window: string) => void
  setPunts: (punts: string[]) => void
  /** Back to the server's .env defaults. */
  reset: () => void
}

export const SettingsContext = createContext<SettingsContextValue | null>(null)

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used inside <SettingsProvider>')
  return ctx
}
