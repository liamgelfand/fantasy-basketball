import { Badge, Group, Paper, SimpleGrid, Stack, Text, Timeline, Title } from '@mantine/core'
import { IconArrowsExchange, IconMinus, IconPlus } from '@tabler/icons-react'
import { useActivity, useStandings } from '../../api/queries'
import type { Activity, Standing } from '../../api/types'
import { DataTable, type Column } from '../../components/DataTable'
import { PageHeader } from '../../components/PageHeader'
import { QueryState } from '../../components/QueryState'

const TROPHIES: Record<number, string> = { 1: '🏆', 2: '🥈', 3: '🥉' }

const standingColumns: Column<Standing>[] = [
  {
    key: 'standing',
    label: '#',
    sortValue: (t) => t.standing,
    render: (t) => (
      <Text size="sm" fw={700}>
        {TROPHIES[t.standing] ?? t.standing}
      </Text>
    ),
  },
  {
    key: 'name',
    label: 'Team',
    sortValue: (t) => t.name,
    render: (t) => (
      <Group gap={6} wrap="nowrap">
        <Text size="sm" fw={t.is_me ? 700 : 500}>
          {t.name}
        </Text>
        {t.is_me && (
          <Badge size="xs" variant="filled">
            You
          </Badge>
        )}
      </Group>
    ),
  },
  { key: 'record', label: 'Record', render: (t) => t.record },
  {
    key: 'pf',
    label: 'Points for',
    align: 'right',
    sortValue: (t) => t.points_for,
    render: (t) => t.points_for.toLocaleString(),
  },
]

export function LeaguePage() {
  const standings = useStandings()
  const activity = useActivity()
  return (
    <Stack gap="lg">
      <PageHeader title="League" />
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Paper p={0}>
          <Title order={4} p="lg" pb="xs">
            Standings
          </Title>
          <QueryState query={standings}>
            {(rows) => (
              <DataTable
                rows={rows}
                columns={standingColumns}
                rowKey={(t) => t.id}
                initialSort={{ key: 'standing', desc: false }}
                highlight={(t) => t.is_me}
                minWidth={360}
              />
            )}
          </QueryState>
        </Paper>
        <Paper>
          <Title order={4} mb="md">
            Recent activity
          </Title>
          <QueryState query={activity}>{(rows) => <ActivityFeed rows={rows} />}</QueryState>
        </Paper>
      </SimpleGrid>
    </Stack>
  )
}

function actionStyle(action: string) {
  const a = action.toUpperCase()
  if (a.includes('DROP')) return { color: 'red', icon: <IconMinus size={12} /> }
  if (a.includes('TRADE')) return { color: 'grape', icon: <IconArrowsExchange size={12} /> }
  return { color: 'teal', icon: <IconPlus size={12} /> }
}

function ActivityFeed({ rows }: { rows: Activity[] }) {
  if (!rows.length) return <Text c="dimmed">Quiet league so far.</Text>
  return (
    <Timeline bulletSize={22} lineWidth={2}>
      {rows.map((r, i) => {
        const style = actionStyle(r.action)
        return (
          <Timeline.Item key={`${r.date}-${r.player}-${i}`} bullet={style.icon} color={style.color}>
            <Text size="sm">
              <b>{r.team}</b> {r.action.toLowerCase()} <b>{r.player}</b>
            </Text>
            <Text size="xs" c="dimmed">
              {r.date}
            </Text>
          </Timeline.Item>
        )
      })}
    </Timeline>
  )
}
