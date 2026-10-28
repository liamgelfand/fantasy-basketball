import { BarChart } from '@mantine/charts'
import { Group, Paper, Text, Title } from '@mantine/core'
import type { StartsDay } from '../../api/types'
import { shortDate } from '../../lib/format'
import { ME_COLOR, OPP_COLOR } from '../../theme'

export function StartsChart({ days, opponent, maxStarts }: { days: StartsDay[]; opponent: string; maxStarts: number }) {
  if (!days.length) return null
  const data = days.map((d) => ({ day: shortDate(d.date), You: d.mine_starts, [opponent]: d.opp_starts }))
  const openSlots = days.reduce((n, d) => n + d.mine_open_slots, 0)
  const benched = days.reduce((n, d) => n + d.mine_benched.length, 0)

  return (
    <Paper>
      <Group justify="space-between" mb="md" align="flex-end">
        <div>
          <Title order={4}>Starts per day</Title>
          <Text size="sm" c="dimmed">
            Where the games are. Open slots are free starts you could stream into.
          </Text>
        </div>
        <Group gap="lg">
          <Text size="sm">
            <b>{openSlots}</b> open slots
          </Text>
          <Text size="sm">
            <b>{benched}</b> benched games
          </Text>
        </Group>
      </Group>
      <BarChart
        h={260}
        data={data}
        dataKey="day"
        series={[
          { name: 'You', color: ME_COLOR },
          { name: opponent, color: OPP_COLOR },
        ]}
        withLegend
        legendProps={{ verticalAlign: 'top', height: 36 }}
        yAxisProps={{ domain: [0, maxStarts], allowDecimals: false }}
        gridAxis="y"
        tickLine="none"
        maxBarWidth={28}
        barProps={{ radius: [6, 6, 0, 0] }}
      />
    </Paper>
  )
}
