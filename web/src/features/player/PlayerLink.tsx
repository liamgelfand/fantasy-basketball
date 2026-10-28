import { UnstyledButton } from '@mantine/core'
import type { ReactNode } from 'react'
import classes from './PlayerLink.module.css'
import { usePlayerDrawer } from './usePlayerDrawer'

/** A player name that opens their card in the app-wide drawer. */
export function PlayerLink({ id, children }: { id: number; children: ReactNode }) {
  const { open } = usePlayerDrawer()
  return (
    <UnstyledButton className={classes.link} onClick={() => open(id)}>
      {children}
    </UnstyledButton>
  )
}
