import {
  Alert,
  Badge,
  Drawer,
  Group,
  Center,
  Loader,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Timeline,
  Title,
} from '@mantine/core'
import { IconNews } from '@tabler/icons-react'
import { useMemo, useState, type ReactNode } from 'react'
import { usePlayer } from '../../api/queries'
import type { PlayerDetail } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { formatStat, longDate, shortDate, signed } from '../../lib/format'
import { PlayerDrawerContext } from './usePlayerDrawer'

const WINDOW_LABELS: Record<string, string> = {
  season: 'Season',
  last_30: 'Last 30',
  last_15: 'Last 15',
  last_7: 'Last 7',
  projected: 'Projected',
  blend: 'Blend',
}

/** One drawer for the whole app: any player name can open it via usePlayerDrawer().open(id). */
export function PlayerDrawerProvider({ children }: { children: ReactNode }) {
  const [playerId, setPlayerId] = useState<number | null>(null)
  const value = useMemo(() => ({ open: setPlayerId }), [])
  return (
    <PlayerDrawerContext.Provider value={value}>
      {children}
      <Drawer
        opened={playerId !== null}
        onClose={() => setPlayerId(null)}
        position="right"
        size="lg"
        title={<Text fw={700}>Player card</Text>}
      >
        {playerId !== null && <PlayerCard id={playerId} />}
      </Drawer>
    </PlayerDrawerContext.Provider>
  )
}

function PlayerCard({ id }: { id: number }) {
  const player = usePlayer(id)
  if (player.isPending) {
    return (
      <Center mih={200}>
        <Loader type="dots" />
      </Center>
    )
  }
  if (player.isError) {
    return (
      <Alert color="red" variant="light">
        {player.error.message}
      </Alert>
    )
  }
  return <PlayerCardView p={player.data} />
}

function PlayerCardView({ p }: { p: PlayerDetail }) {
  const windows = Object.keys(p.windows)
  const stats = windows.length ? Object.keys(p.windows[windows[0]]) : []
  return (
    <Stack gap="lg">
      <div>
        <Group gap="xs">
          <Title order={2}>{p.name}</Title>
          <StatusBadge status={p.status} />
        </Group>
        <Text c="dimmed">
          {p.pro_team} · {p.positions.join('/') || '—'} ·{' '}
          {p.owner ? (p.is_mine ? 'On your team' : `Owned by ${p.owner}`) : 'Free agent'}
        </Text>
        {p.expected_return && (
          <Text size="sm" c="orange" mt={4}>
            Expected back {longDate(p.expected_return)}
          </Text>
        )}
      </div>

      <SimpleGrid cols={3}>
        <Fact label="Value" value={signed(p.value)} />
        <Fact label="Games left" value={`${p.games_left} this wk`} />
        <Fact label="Rest of season" value={`${p.ros_games} games`} />
      </SimpleGrid>

      {windows.length > 0 && (
        <div>
          <Text fw={700} mb="xs">
            Per-game stats
          </Text>
          <Table.ScrollContainer minWidth={420}>
            <Table striped verticalSpacing={4} fz="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th />
                  {stats.map((s) => (
                    <Table.Th key={s} ta="right">
                      {s}
                    </Table.Th>
                  ))}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {windows.map((w) => (
                  <Table.Tr key={w}>
                    <Table.Td fw={600} style={{ whiteSpace: 'nowrap' }}>
                      {WINDOW_LABELS[w] ?? w}
                      {w === p.stat_window && (
                        <Badge size="xs" ml={4} variant="light">
                          used
                        </Badge>
                      )}
                    </Table.Td>
                    {stats.map((s) => (
                      <Table.Td key={s} ta="right">
                        {formatStat(s, p.windows[w][s] ?? 0)}
                      </Table.Td>
                    ))}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </div>
      )}

      {p.upcoming_games.length > 0 && (
        <div>
          <Text fw={700} mb="xs">
            Upcoming games
          </Text>
          <Group gap={6}>
            {p.upcoming_games.map((d) => (
              <Badge key={d} variant="light" color="indigo">
                {shortDate(d)}
              </Badge>
            ))}
          </Group>
        </div>
      )}

      <div>
        <Text fw={700} mb="xs">
          Latest news
        </Text>
        {p.news_error && (
          <Text size="sm" c="dimmed">
            {p.news_error}
          </Text>
        )}
        {!p.news_error && p.news.length === 0 && (
          <Text size="sm" c="dimmed">
            No recent news.
          </Text>
        )}
        <Timeline bulletSize={20} lineWidth={2}>
          {p.news.map((n, i) => (
            <Timeline.Item key={i} bullet={<IconNews size={12} />} title={<Text size="sm" fw={600}>{n.headline}</Text>}>
              {n.story && (
                <Text size="xs" c="dimmed" lineClamp={4}>
                  {n.story}
                </Text>
              )}
              {n.published && (
                <Text size="xs" c="dimmed" mt={2}>
                  {new Date(n.published).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
                </Text>
              )}
            </Timeline.Item>
          ))}
        </Timeline>
      </div>
    </Stack>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
        {label}
      </Text>
      <Text fw={700} ff="heading" size="lg">
        {value}
      </Text>
    </div>
  )
}
