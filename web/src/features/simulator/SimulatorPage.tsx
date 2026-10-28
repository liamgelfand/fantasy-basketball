import { BarChart } from '@mantine/charts'
import { Alert, Button, Group, MultiSelect, Paper, SimpleGrid, Stack, TagsInput, Text, Title } from '@mantine/core'
import { IconCalendarEvent, IconFlask, IconTarget, IconTrendingUp, IconTrophy } from '@tabler/icons-react'
import { useState } from 'react'
import { useFreeAgents, useMeta, useRoster, useSimulate } from '../../api/queries'
import type { MoveResult } from '../../api/types'
import { Delta } from '../../components/Delta'
import { PageHeader } from '../../components/PageHeader'
import { StatCard } from '../../components/StatCard'
import { pct, signed, signedPct } from '../../lib/format'

export function SimulatorPage() {
  const [add, setAdd] = useState<string[]>([])
  const [drop, setDrop] = useState<string[]>([])
  const freeAgents = useFreeAgents(null, true)
  const roster = useRoster()
  const meta = useMeta()
  const simulate = useSimulate()

  return (
    <Stack gap="lg">
      <PageHeader title="Move simulator" subtitle="Re-projects this matchup, lineup-aware, after the moves you pick" />
      <Paper>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TagsInput
            label="Add"
            description="Pick free agents, or type any player's name and press Enter"
            placeholder="e.g. a hot streamer"
            data={freeAgents.data?.rows.map((r) => r.name) ?? []}
            value={add}
            onChange={setAdd}
            clearable
          />
          <MultiSelect
            label="Drop"
            description="Players from your roster"
            placeholder="Who goes?"
            data={roster.data?.players.map((p) => p.name) ?? []}
            value={drop}
            onChange={setDrop}
            searchable
            clearable
          />
        </SimpleGrid>
        <Group justify="flex-end" mt="md">
          <Button
            leftSection={<IconFlask size={18} />}
            disabled={!add.length && !drop.length}
            loading={simulate.isPending}
            onClick={() => simulate.mutate({ add, drop })}
          >
            Simulate
          </Button>
        </Group>
      </Paper>

      {simulate.isError && (
        <Alert color="red" variant="light" title="Couldn't simulate">
          {simulate.error.message}
        </Alert>
      )}
      {simulate.data && <SimulationResult res={simulate.data} isPoints={!!meta.data?.is_points} />}
    </Stack>
  )
}

function SimulationResult({ res, isPoints }: { res: MoveResult; isPoints: boolean }) {
  const winDelta = res.win_prob_after - res.win_prob_before
  const deltas = Object.entries(res.category_deltas).map(([stat, d]) => ({ stat, 'Win % change': d * 100 }))
  const verdict = winDelta > 0.02 ? '✅ Worth it' : winDelta < -0.02 ? '🚫 Hurts you' : '🤷 Basically a wash'

  return (
    <Stack gap="lg">
      <Group gap="sm">
        <Title order={3}>{verdict}</Title>
        <Text c="dimmed">for this matchup</Text>
      </Group>
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
        {isPoints ? (
          <StatCard
            label="Projected FPTS"
            value={signed(res.projected_delta.FPTS ?? 0)}
            icon={<IconTarget />}
            color="indigo"
          />
        ) : (
          <StatCard
            label="Expected cats won"
            value={res.expected_wins_after.toFixed(2)}
            hint={<Delta value={res.matchup_gain}>{signed(res.matchup_gain, 2)}</Delta>}
            icon={<IconTarget />}
            color="indigo"
          />
        )}
        <StatCard
          label="Win probability"
          value={pct(res.win_prob_after)}
          hint={<Delta value={winDelta}>{signedPct(winDelta)}</Delta>}
          icon={<IconTrophy />}
          color="yellow"
        />
        <StatCard label="Starts this matchup" value={signed(res.games_delta, 0)} icon={<IconCalendarEvent />} color="teal" />
        <StatCard label="Season value" value={signed(res.season_value_delta)} icon={<IconTrendingUp />} />
      </SimpleGrid>
      {res.notes.map((n) => (
        <Alert key={n} color="yellow" variant="light">
          {n}
        </Alert>
      ))}
      {!isPoints && (
        <Paper>
          <Title order={4} mb="md">
            Category win odds change
          </Title>
          <BarChart
            h={Math.max(220, deltas.length * 32)}
            data={deltas}
            dataKey="stat"
            orientation="vertical"
            series={[{ name: 'Win % change', color: 'indigo.6' }]}
            getBarColor={(v) => (v >= 0 ? 'teal.6' : 'red.6')}
            valueFormatter={(v) => `${signed(v, 1)}%`}
            referenceLines={[{ x: 0, color: 'gray.5' }]}
            gridAxis="x"
            tickLine="none"
            barProps={{ radius: 4 }}
          />
        </Paper>
      )}
    </Stack>
  )
}
