import { ScatterChart } from '@mantine/charts'
import { Badge, Card, Group, Paper, SegmentedControl, SimpleGrid, Stack, Switch, Text, Title } from '@mantine/core'
import { IconAlertCircle } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { useFreeAgents, useMeta } from '../../api/queries'
import type { FreeAgentBoard, FreeAgentRow, Position } from '../../api/types'
import { DataTable, type Column } from '../../components/DataTable'
import { PageHeader } from '../../components/PageHeader'
import { nameColumn, numberColumn, valueColumn } from '../../components/playerColumns'
import { QueryState } from '../../components/QueryState'
import { StatusBadge } from '../../components/StatusBadge'
import { PlayerLink } from '../player/PlayerLink'
import { pct, shortDate, signed } from '../../lib/format'
import { MovePlanCard } from './MovePlanCard'

const POSITIONS = ['All', 'PG', 'SG', 'SF', 'PF', 'C', 'G', 'F'] as const
const MEDALS = ['🥇', '🥈', '🥉']
const OUTLOOKS: Record<NonNullable<FreeAgentRow['outlook']>, { label: string; color: string; hint: string }> = {
  streamer: { label: 'Streamer', color: 'orange', hint: 'Helps this matchup only' },
  stash: { label: 'Stash', color: 'grape', hint: 'Long-term value, low impact this matchup' },
  both: { label: 'Now + later', color: 'teal', hint: 'Helps this matchup and long term' },
}

function OutlookBadge({ row }: { row: FreeAgentRow }) {
  if (!row.outlook) return null
  const o = OUTLOOKS[row.outlook]
  return (
    <Badge variant="light" color={o.color} title={[o.hint, ...row.notes].join(' ')}>
      {o.label}
    </Badge>
  )
}

export function FreeAgentsPage() {
  const [position, setPosition] = useState<(typeof POSITIONS)[number]>('All')
  const [includeInjured, setIncludeInjured] = useState(false)
  const board = useFreeAgents(position === 'All' ? null : (position as Position), includeInjured)
  const meta = useMeta()
  const isPoints = !!meta.data?.is_points

  return (
    <Stack gap="lg">
      <PageHeader
        title="Free agents"
        subtitle="Each pickup is simulated on its next game day against your weakest roster spots"
      />
      <MovePlanCard isPoints={isPoints} />
      <Group justify="space-between" wrap="wrap">
        <SegmentedControl value={position} onChange={(v) => setPosition(v as typeof position)} data={[...POSITIONS]} />
        <Switch
          label="Include injured players"
          checked={includeInjured}
          onChange={(e) => setIncludeInjured(e.currentTarget.checked)}
        />
      </Group>
      <QueryState query={board} loadingLabel={`Scoring ${position === 'All' ? '' : `${position} `}free agents…`}>
        {(b) => <BoardView board={b} isPoints={isPoints} />}
      </QueryState>
    </Stack>
  )
}

function gainText(gain: number, isPoints: boolean): string {
  return isPoints ? `${signed(gain, 0)} FPTS` : `${signed(gain, 2)} cats`
}

function BoardView({ board, isPoints }: { board: FreeAgentBoard; isPoints: boolean }) {
  const columns = useMemo<Column<FreeAgentRow>[]>(
    () => [
      nameColumn(),
      {
        key: 'gain',
        label: board.gain_label,
        align: 'right',
        sortValue: (r) => r.matchup_gain,
        render: (r) => (
          <Text size="sm" fw={700} c={r.matchup_gain > 0 ? 'teal' : 'dimmed'}>
            {signed(r.matchup_gain, isPoints ? 1 : 2)}
          </Text>
        ),
      },
      {
        key: 'win',
        label: 'Win % after',
        align: 'right',
        sortValue: (r) => r.win_prob_after,
        render: (r) => pct(r.win_prob_after),
      },
      {
        key: 'drop',
        label: 'Best drop',
        sortValue: (r) => r.best_drop ?? '',
        render: (r) => (r.best_drop ? <Text size="sm">{r.best_drop}</Text> : <Badge variant="light">Open spot</Badge>),
      },
      {
        key: 'add_date',
        label: 'Add on',
        sortValue: (r) => r.add_date ?? '',
        render: (r) => (r.add_date ? shortDate(r.add_date) : '-'),
      },
      {
        key: 'outlook',
        label: 'Horizon',
        sortValue: (r) => r.outlook ?? '',
        render: (r) => <OutlookBadge row={r} />,
      },
      valueColumn(),
      numberColumn('ros_value', 'ROS value', (r) => r.ros_value, 1),
      numberColumn('games_left', 'G left', (r) => r.games_left),
      numberColumn('fpts', 'FPTS/g', (r) => r.fpts, 1),
      numberColumn('min', 'MIN', (r) => r.minutes, 1),
      {
        key: 'gp',
        label: 'GP',
        align: 'right',
        sortValue: (r) => r.gp,
        render: (r) => (
          <Group gap={4} justify="flex-end" wrap="nowrap">
            {r.low_sample && <IconAlertCircle size={14} color="var(--mantine-color-yellow-6)" />}
            {r.gp}
          </Group>
        ),
      },
    ],
    [board.gain_label, isPoints],
  )

  if (!board.rows.length) {
    return (
      <Paper>
        <Text c="dimmed">No free agents match these filters.</Text>
      </Paper>
    )
  }

  const top = board.rows.slice(0, 3)
  // Points carry the row index so the tooltip can name the player (series data must be numeric).
  const scatter = [
    {
      name: 'Free agents',
      color: 'court.6',
      data: board.rows.map((r, i) => ({ value: r.value, gain: r.matchup_gain, row: i })),
    },
  ]

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {top.map((r, i) => (
          <Card key={r.id} padding="lg">
            <Group justify="space-between" mb="xs" wrap="nowrap">
              <Text fz={28} aria-hidden>
                {MEDALS[i]}
              </Text>
              <Badge size="lg" variant="gradient" gradient={{ from: 'court', to: 'grape' }}>
                {gainText(r.matchup_gain, isPoints)}
              </Badge>
            </Group>
            <Group gap={6}>
              <Title order={4}>
                <PlayerLink id={r.id}>{r.name}</PlayerLink>
              </Title>
              <StatusBadge status={r.status} />
              <OutlookBadge row={r} />
            </Group>
            <Text size="sm" c="dimmed">
              {r.pro_team} · {r.positions.join('/')} · {r.games_left} games left
            </Text>
            <Text size="sm" mt="sm">
              {r.best_drop ? (
                <>
                  Drop <b>{r.best_drop}</b>
                </>
              ) : (
                'Use your open roster spot'
              )}
              {r.add_date && <> on {shortDate(r.add_date)}</>} → {pct(r.win_prob_after)} to win
            </Text>
          </Card>
        ))}
      </SimpleGrid>

      <Paper>
        <Title order={4} mb={4}>
          Now vs later
        </Title>
        <Text size="sm" c="dimmed" mb="md">
          Top-right helps this week <i>and</i> long term
        </Text>
        <ScatterChart
          h={320}
          data={scatter}
          dataKey={{ x: 'value', y: 'gain' }}
          labels={{ x: 'Season value (z)', y: board.gain_label }}
          valueFormatter={{ x: (v) => v.toFixed(1), y: (v) => v.toFixed(isPoints ? 1 : 2) }}
          referenceLines={[{ y: 0, color: 'gray.5' }]}
          tooltipProps={{
            content: ({ payload }) => {
              const point = payload?.[0]?.payload as { row?: number } | undefined
              const r = point?.row === undefined ? undefined : board.rows[point.row]
              return r ? <ScatterTip row={r} gainLabel={board.gain_label} isPoints={isPoints} /> : null
            },
          }}
        />
      </Paper>

      <Paper p={0}>
        <DataTable
          rows={board.rows}
          columns={columns}
          rowKey={(r) => r.id}
          initialSort={{ key: 'gain', desc: true }}
          minWidth={980}
          maxHeight={640}
        />
      </Paper>
      {board.rows.some((r) => r.low_sample) && (
        <Text size="xs" c="dimmed">
          <IconAlertCircle size={12} color="var(--mantine-color-yellow-6)" /> Under 5 games played: rankings still
          lean partly on ESPN's preseason projection. Check their minutes before trusting them.
        </Text>
      )}
    </Stack>
  )
}

function ScatterTip({ row, gainLabel, isPoints }: { row: FreeAgentRow; gainLabel: string; isPoints: boolean }) {
  return (
    <Paper p="xs" shadow="md" withBorder radius="md">
      <Text fw={700} size="sm">
        {row.name}
      </Text>
      <Text size="xs" c="dimmed">
        {row.pro_team} · {row.positions.join('/')} · {row.games_left} games left
      </Text>
      <Text size="xs" mt={4}>
        {gainLabel}: <b>{signed(row.matchup_gain, isPoints ? 1 : 2)}</b> · Season value: <b>{signed(row.value)}</b>
      </Text>
      <Text size="xs">{row.best_drop ? `Best drop: ${row.best_drop}` : 'Uses your open spot'}</Text>
    </Paper>
  )
}
