import { createContext, useContext } from 'react'

export interface PlayerDrawerContextValue {
  open: (playerId: number) => void
}

export const PlayerDrawerContext = createContext<PlayerDrawerContextValue | null>(null)

export function usePlayerDrawer(): PlayerDrawerContextValue {
  const ctx = useContext(PlayerDrawerContext)
  if (!ctx) throw new Error('usePlayerDrawer must be used inside <PlayerDrawerProvider>')
  return ctx
}
