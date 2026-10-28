import { BarChart } from '@mantine/charts'
import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useMemo } from 'react'
import { useMeta, useRoster } from '../../api/queries'
import type { PlayerRow, Roster } from '../../api/types'
import { DataTable, type Column } from '../../components/DataTable'
import { PageHeader } from '../../components/PageHeader'
import { nameColumn, numberColumn, statColumns, valueColumn } from '../../components/playerColumns'
import { QueryState } from '../../components/QueryState'
import { signed } from '../../lib/format'

export function RosterPage() {
  const roster = useRoster()
  const meta = useMeta()
  return <QueryState query={roster}>{(r) => <RosterView roster={r} isPoints={!!meta.data?.is_points} />}</QueryState>
}

function RosterView({ roster, isPoints }: { roster: Roster; isPoints: boolean }) {
  const columns = useMemo<Column<PlayerRow>[]>(
    () => [
      {
        key: 'slot',
        label: 'Slot',
        sortValue: (p) => p.lineup_slot ?? '',
        render: (p) => (
          <Badge variant={p.lineup_slot === 'BE' || p.lineup_slot === 'IR' ? 'outline' : 'light'} color="gray">
            {p.lineup_slot ?? '—'}
          </Badge>
        ),
      },
      nameColumn(),
      valueColumn(),
      numberColumn('games_left', 'G left', (p) => p.games_left),
      numberColumn('ros_games', 'ROS G', (p) => p.ros_games),
      numberColumn('gp', 'GP', (p) => p.gp),
      numberColumn('min', 'MIN', (p) => p.minutes, 1),
      ...statColumns<PlayerRow>(roster.stats),
    ],
    [roster.stats],
  )

  const metric = isPoints ? 'FPTS/g' : 'Value'
  const chartData = [...roster.players]
    .map((p) => ({ player: p.name, [metric]: isPoints ? p.fpts : p.value }))
    .sort((a, b) => (b[metric] as number) - (a[metric] as number))

  return (
    <Stack gap="lg">
      <PageHeader
        title="Your roster"
        subtitle={`${roster.team.name} · ${roster.team.record}`}
        right={
          <Group gap="xs">
            <Text size="sm" c="dimmed">
              Weakest spots:
            </Text>
            {roster.weakest.map((w) => (
              <Badge key={w.name} color="red" variant="light">
                {w.name} {signed(w.value)}
              </Badge>
            ))}
          </Group>
        }
      />
      <Paper p={0}>
        <DataTable rows={roster.players} columns={columns} rowKey={(p) => p.id} minWidth={900} />
      </Paper>
      <Paper>
        <Title order={4} mb={4}>
          {isPoints ? 'Fantasy points per game' : 'Player value'}
        </Title>
        <Text size="sm" c="dimmed" mb="md">
          {isPoints ? 'Per-game production in your scoring' : 'Per-game z-score total vs every rostered player'}
        </Text>
        <BarChart
          h={Math.max(240, chartData.length * 30)}
          data={chartData}
          dataKey="player"
          orientation="vertical"
          series={[{ name: metric, color: 'indigo.6' }]}
          getBarColor={(v) => (v >= 0 ? 'indigo.6' : 'red.5')}
          yAxisProps={{ width: 140 }}
          gridAxis="x"
          tickLine="none"
          valueFormatter={(v) => v.toFixed(1)}
          barProps={{ radius: 4 }}
        />
      </Paper>
    </Stack>
  )
}
