import { Alert, Button, Group, MultiSelect, Paper, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconArrowsExchange, IconCalendarStats, IconTarget, IconTrendingUp } from '@tabler/icons-react'
import { useState } from 'react'
import { useEvaluateTrade, useMeta, useRoster, useTeamRoster } from '../../api/queries'
import type { TradeResult } from '../../api/types'
import { DeltaBars } from '../../components/DeltaBars'
import { PageHeader } from '../../components/PageHeader'
import { StatCard } from '../../components/StatCard'
import { isRatio, signed } from '../../lib/format'

export function TradesPage() {
  const meta = useMeta()
  const roster = useRoster()
  const [partnerId, setPartnerId] = useState<number | null>(null)
  const [give, setGive] = useState<string[]>([])
  const [get, setGet] = useState<string[]>([])
  const partner = useTeamRoster(partnerId)
  const evaluate = useEvaluateTrade()

  const partners = meta.data?.teams.filter((t) => t.id !== meta.data?.my_team.id) ?? []

  const pickPartner = (id: string | null) => {
    setPartnerId(id ? Number(id) : null)
    setGet([])
    evaluate.reset()
  }

  return (
    <Stack gap="lg">
      <PageHeader title="Trade analyzer" subtitle="See what a deal does to your categories, schedule and this matchup" />
      <Paper>
        <Stack>
          <Select
            label="Trade partner"
            placeholder="Pick a team"
            data={partners.map((t) => ({ value: String(t.id), label: `${t.name} (${t.record})` }))}
            value={partnerId === null ? null : String(partnerId)}
            onChange={pickPartner}
            searchable
          />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <MultiSelect
              label="You give"
              data={roster.data?.players.map((p) => p.name) ?? []}
              value={give}
              onChange={setGive}
              searchable
            />
            <MultiSelect
              label="You get"
              data={partner.data?.players ?? []}
              value={get}
              onChange={setGet}
              disabled={partnerId === null}
              placeholder={partnerId === null ? 'Pick a partner first' : undefined}
              searchable
            />
          </SimpleGrid>
          <Group justify="flex-end">
            <Button
              leftSection={<IconArrowsExchange size={18} />}
              disabled={partnerId === null || !give.length || !get.length}
              loading={evaluate.isPending}
              onClick={() => partnerId !== null && evaluate.mutate({ partnerId, give, get })}
            >
              Evaluate trade
            </Button>
          </Group>
        </Stack>
      </Paper>

      {evaluate.isError && (
        <Alert color="red" variant="light" title="Couldn't evaluate">
          {evaluate.error.message}
        </Alert>
      )}
      {evaluate.data && meta.data && (
        <TradeView
          result={evaluate.data}
          isPoints={meta.data.is_points}
          reverse={['TO', ...meta.data.categories.filter((c) => c.reverse).map((c) => c.stat)]}
        />
      )}
    </Stack>
  )
}

function TradeView({ result, isPoints, reverse }: { result: TradeResult; isPoints: boolean; reverse: string[] }) {
  const rows = Object.entries(result.per_game_change).map(([stat, value]) => ({ stat, value }))
  const verdict =
    result.value_change > 0.5 ? '🤝 You win this trade' : result.value_change < -0.5 ? '🙅 You lose this trade' : '⚖️ Pretty even'

  return (
    <Stack gap="lg">
      <Title order={3}>{verdict}</Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <StatCard label="Season value" value={signed(result.value_change, 2)} icon={<IconTrendingUp />} />
        <StatCard
          label="Rest-of-season games"
          value={signed(result.ros_games_change, 0)}
          icon={<IconCalendarStats />}
          color="teal"
        />
        <StatCard
          label={isPoints ? 'This matchup (FPTS)' : 'This matchup (cats)'}
          value={result.matchup_change === null ? '—' : signed(result.matchup_change, isPoints ? 1 : 2)}
          icon={<IconTarget />}
          color="indigo"
        />
      </SimpleGrid>
      {result.roster_overflow > 0 && (
        <Alert color="yellow" variant="light">
          You'd need to drop {result.roster_overflow} player{result.roster_overflow > 1 ? 's' : ''} to make room.
        </Alert>
      )}
      <Paper>
        <Title order={4} mb={4}>
          Per-game change
        </Title>
        <Text size="sm" c="dimmed" mb="md">
          What you get minus what you give, per game
        </Text>
        <DeltaBars rows={rows} format={(v, stat) => signed(v, isRatio(stat) ? 3 : 2)} reverse={reverse} />
      </Paper>
    </Stack>
  )
}
