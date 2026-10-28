import { Alert, Stack } from '@mantine/core'
import { IconFirstAidKit, IconSwitchHorizontal } from '@tabler/icons-react'
import type { Matchup } from '../../api/types'

export function LineupAlerts({ lineup }: { lineup: Matchup['lineup'] }) {
  if (!lineup.start.length && !lineup.ir_candidates.length) return null
  return (
    <Stack gap="xs">
      {lineup.start.length > 0 && (
        <Alert
          color="court"
          variant="light"
          icon={<IconSwitchHorizontal />}
          title={lineup.games_started ? "Today's lineup (games already started)" : "Fix today's lineup"}
        >
          Start <b>{lineup.start.join(', ')}</b>
          {lineup.bench.length > 0 && <> over {lineup.bench.join(', ')}</>}.
        </Alert>
      )}
      {lineup.ir_candidates.map((name) => (
        <Alert key={name} color="red" variant="light" icon={<IconFirstAidKit />}>
          <b>{name}</b> is out. Move to IR if your slot is open.
        </Alert>
      ))}
    </Stack>
  )
}
