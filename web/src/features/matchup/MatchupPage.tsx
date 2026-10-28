import { Alert, Group, Paper, RingProgress, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { IconBallBasketball, IconCalendarEvent, IconTarget, IconTrophy } from '@tabler/icons-react'
import { useMatchup, useMeta } from '../../api/queries'
import type { LeagueMeta, Matchup } from '../../api/types'
import { PageHeader } from '../../components/PageHeader'
import { QueryState } from '../../components/QueryState'
import { StatCard } from '../../components/StatCard'
import { longDate, pct, probColor, probEmoji, signed } from '../../lib/format'
import { CategoryBoard } from './CategoryBoard'
import { LineupAlerts } from './LineupAlerts'
import { ScheduleGrid } from './ScheduleGrid'
import { StartsChart } from './StartsChart'
import classes from './MatchupPage.module.css'

export function MatchupPage() {
  const meta = useMeta()
  const matchup = useMatchup()
  return (
    <QueryState query={matchup}>
      {(m) => (meta.data ? <MatchupView meta={meta.data} m={m} /> : null)}
    </QueryState>
  )
}

function MatchupView({ meta, m }: { meta: LeagueMeta; m: Matchup }) {
  if (!m.opponent) {
    return (
      <>
        <PageHeader title="Matchup" />
        <Alert variant="light" title="No active matchup">
          Bye week or off-season. Check back when the next matchup starts.
        </Alert>
        <LineupAlerts lineup={m.lineup} />
      </>
    )
  }

  const points = meta.is_points ? m.categories[0] : null
  return (
    <Stack gap="lg">
      <Paper className={classes.hero} p="xl">
        <Group justify="space-between" wrap="wrap" gap="lg">
          <Stack gap={4}>
            <Text size="sm" fw={600} c="dimmed" tt="uppercase" lts={1}>
              This week {m.start_date && m.end_date && `· ${longDate(m.start_date)} to ${longDate(m.end_date)}`}
            </Text>
            <Title order={1} className={classes.versus}>
              {meta.my_team.name} <span className={classes.vs}>vs</span> {m.opponent.name}
            </Title>
            <Text c="dimmed">
              {meta.my_team.record} vs {m.opponent.record} · {m.days_left} {m.days_left === 1 ? 'day' : 'days'} left
            </Text>
          </Stack>
          <Group gap="md" wrap="nowrap">
            <RingProgress
              size={132}
              thickness={12}
              roundCaps
              sections={[{ value: m.win_prob * 100, color: probColor(m.win_prob) }]}
              label={
                <Stack gap={0} align="center">
                  <Text fw={800} size="xl" ff="heading">
                    {pct(m.win_prob)}
                  </Text>
                  <Text size="xs" c="dimmed">
                    to win
                  </Text>
                </Stack>
              }
            />
            <Text fz={44} aria-hidden>
              {probEmoji(m.win_prob)}
            </Text>
          </Group>
        </Group>
      </Paper>

      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
        {points ? (
          <>
            <StatCard
              label="Score now"
              value={`${Math.round(points.mine_now)}–${Math.round(points.theirs_now)}`}
              hint={`${signed(points.mine_now - points.theirs_now, 0)} margin`}
              icon={<IconBallBasketball />}
            />
            <StatCard
              label="Projected final"
              value={`${Math.round(points.mine_final)}–${Math.round(points.theirs_final)}`}
              hint={`${signed(points.mine_final - points.theirs_final, 0)} ± ${Math.round(m.points_margin_sd ?? 0)}`}
              icon={<IconTarget />}
              color="indigo"
            />
          </>
        ) : (
          <>
            <StatCard
              label="Expected cats won"
              value={`${m.expected_wins.toFixed(1)} / ${m.categories_total}`}
              hint="Sum of category win odds"
              icon={<IconTarget />}
              color="indigo"
            />
            <StatCard
              label="Swing categories"
              value={m.categories.filter((c) => c.win_prob > 0.3 && c.win_prob < 0.7).length}
              hint="Between 30% and 70%: where moves matter"
              icon={<IconBallBasketball />}
            />
          </>
        )}
        <StatCard
          label="Starts left"
          value={`${Math.round(m.my_starts_left)}–${Math.round(m.opp_starts_left)}`}
          hint={`${signed(m.my_starts_left - m.opp_starts_left, 0)} vs opponent`}
          icon={<IconCalendarEvent />}
          color="teal"
        />
        <StatCard
          label="Standing"
          value={`#${meta.my_team.standing}`}
          hint={`of ${meta.teams.length} teams`}
          icon={<IconTrophy />}
          color="yellow"
        />
      </SimpleGrid>

      <LineupAlerts lineup={m.lineup} />

      {!points && <CategoryBoard categories={m.categories} punts={meta.punt_categories} />}

      <StartsChart days={m.days} opponent={m.opponent.name} maxStarts={meta.lineup_slots.length} />
      <ScheduleGrid schedule={m.schedule} />
    </Stack>
  )
}
