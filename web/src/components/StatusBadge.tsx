import { Badge } from '@mantine/core'
import { titleCase } from '../lib/format'

const COLORS: Record<string, string> = {
  OUT: 'red',
  INJURY_RESERVE: 'red',
  SUSPENSION: 'grape',
  DOUBTFUL: 'orange',
  QUESTIONABLE: 'yellow',
  DAY_TO_DAY: 'yellow',
}

const SHORT: Record<string, string> = { DAY_TO_DAY: 'DTD', INJURY_RESERVE: 'IR', QUESTIONABLE: 'Q', DOUBTFUL: 'D' }

export function StatusBadge({ status }: { status: string }) {
  if (!status || status === 'ACTIVE') return null
  return (
    <Badge size="xs" variant="light" color={COLORS[status] ?? 'gray'} title={titleCase(status)}>
      {SHORT[status] ?? titleCase(status)}
    </Badge>
  )
}
