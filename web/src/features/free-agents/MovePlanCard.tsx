import { Badge, Group, Paper, Stack, Text, Timeline, Title } from '@mantine/core'
import { IconCalendarEvent, IconInfoCircle } from '@tabler/icons-react'
import { useMovePlan } from '../../api/queries'
import type { MovePlan, PlannedMove } from '../../api/types'
import { QueryState } from '../../components/QueryState'
import { longDate, pct, signed } from '../../lib/format'
import { PlayerLink } from '../player/PlayerLink'

export function MovePlanCard({ isPoints }: { isPoints: boolean }) {
  const plan = useMovePlan()
  return (
    <QueryState query={plan} loadingLabel="Planning add/drops day by day…">
      {(p) => <PlanView plan={p} isPoints={isPoints} />}
    </QueryState>
  )
}

function dayLabel(m: PlannedMove): string {
  if (m.is_today) return 'Today'
  return m.date ? longDate(m.date) : 'Later'
}

function PlanView({ plan, isPoints }: { plan: MovePlan; isPoints: boolean }) {
  const digits = isPoints ? 1 : 2
  return (
    <Paper>
      <Group justify="space-between" mb="xs" wrap="wrap">
        <Title order={4}>Add/drop plan by day</Title>
        <Group gap="xs">
          {plan.weekly_add_limit !== null && plan.adds_used_this_week !== null && (
            <Badge variant="light" color={plan.capped ? 'orange' : 'gray'}>
              {plan.adds_used_this_week} of {plan.weekly_add_limit} adds used this week
            </Badge>
          )}
          {plan.moves.length > 0 && (
            <Badge variant="light" color="teal">
              {signed(plan.total_gain, digits)} · {pct(plan.win_prob_before)} → {pct(plan.win_prob_after)} to win
            </Badge>
          )}
        </Group>
      </Group>
      {plan.moves.length === 0 ? (
        <Text size="sm" c="dimmed">
          No add/drop improves this matchup enough to recommend.
        </Text>
      ) : (
        <Timeline bulletSize={22} lineWidth={2} active={plan.moves.length - 1} mt="sm">
          {plan.moves.map((m, i) => (
            <Timeline.Item
              key={`${m.add_id}-${i}`}
              bullet={<IconCalendarEvent size={12} />}
              title={
                <Group gap={6} wrap="wrap">
                  <Text fw={700} size="sm">
                    {dayLabel(m)}:
                  </Text>
                  <Text size="sm">
                    add <PlayerLink id={m.add_id}>{m.add}</PlayerLink> ({m.add_positions.join('/')})
                    {m.drop ? (
                      <>
                        , drop <b>{m.drop}</b>
                      </>
                    ) : (
                      ', no drop needed'
                    )}
                  </Text>
                  {m.fills.length > 0 && (
                    <Badge size="sm" variant="light" color="court">
                      fills empty {m.fills.join('/')}
                    </Badge>
                  )}
                  <Badge size="sm" variant="light" color="teal">
                    {signed(m.matchup_gain, digits)} {plan.gain_label.replace(/ gain$/, '')}
                  </Badge>
                </Group>
              }
            >
              <Stack gap={0}>
                {m.notes.map((n) => (
                  <Text key={n} size="xs" c="dimmed">
                    {n}
                  </Text>
                ))}
              </Stack>
            </Timeline.Item>
          ))}
        </Timeline>
      )}
      {plan.notes.map((n) => (
        <Group key={n} gap={4} mt="xs" wrap="nowrap" align="flex-start">
          <IconInfoCircle size={14} color="var(--mantine-color-dimmed)" />
          <Text size="xs" c="dimmed">
            {n}
          </Text>
        </Group>
      ))}
    </Paper>
  )
}
