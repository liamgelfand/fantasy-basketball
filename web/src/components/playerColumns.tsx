import { Badge, Group, Text } from '@mantine/core'
import type { PlayerRow } from '../api/types'
import { PlayerLink } from '../features/player/PlayerLink'
import { formatStat, signed } from '../lib/format'
import type { Column } from './DataTable'
import { StatusBadge } from './StatusBadge'

export function nameColumn<T extends PlayerRow>(): Column<T> {
  return {
    key: 'name',
    label: 'Player',
    sticky: true,
    sortValue: (p) => p.name,
    render: (p) => (
      <Group gap={6} wrap="nowrap">
        <div>
          <PlayerLink id={p.id}>{p.name}</PlayerLink>
          <Text size="xs" c="dimmed">
            {p.pro_team} · {p.positions.join('/') || '—'}
          </Text>
        </div>
        <StatusBadge status={p.status} />
      </Group>
    ),
  }
}

export function valueColumn<T extends PlayerRow>(): Column<T> {
  return {
    key: 'value',
    label: 'Value',
    align: 'right',
    title: 'Sum of per-game z-scores vs every rostered player',
    sortValue: (p) => p.value,
    render: (p) => (
      <Badge variant="light" color={p.value >= 2 ? 'teal' : p.value >= 0 ? 'blue' : 'red'} w={56}>
        {signed(p.value)}
      </Badge>
    ),
  }
}

export function numberColumn<T extends PlayerRow>(
  key: string,
  label: string,
  get: (p: T) => number,
  digits = 0,
): Column<T> {
  return { key, label, align: 'right', sortValue: get, render: (p) => get(p).toFixed(digits) }
}

export function statColumns<T extends PlayerRow>(stats: string[]): Column<T>[] {
  return stats.map((s) => ({
    key: `stat:${s}`,
    label: s,
    align: 'right',
    sortValue: (p: T) => p.stats[s] ?? 0,
    render: (p: T) => formatStat(s, p.stats[s] ?? 0),
  }))
}
