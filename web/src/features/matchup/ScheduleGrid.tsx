import { Box, Group, Paper, Table, Text, Title, Tooltip } from '@mantine/core'
import type { CellState, Matchup } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { shortDate } from '../../lib/format'
import { PlayerLink } from '../player/PlayerLink'
import classes from './ScheduleGrid.module.css'

const CELL: Record<CellState, { label: string; className: string }> = {
  starts: { label: 'Starts', className: classes.starts },
  bench: { label: 'Plays, but no open slot', className: classes.bench },
  out: { label: 'Out / IR', className: classes.out },
}

export function ScheduleGrid({ schedule }: { schedule: Matchup['schedule'] }) {
  if (!schedule.rows.length) return null
  return (
    <Paper>
      <Group justify="space-between" mb="md" align="flex-end">
        <div>
          <Title order={4}>Your schedule</Title>
          <Text size="sm" c="dimmed">
            Who plays each remaining day, and whether they get a starting slot
          </Text>
        </div>
        <Group gap="md">
          {(Object.keys(CELL) as CellState[]).map((s) => (
            <Group key={s} gap={6}>
              <Box className={`${classes.dot} ${CELL[s].className}`} />
              <Text size="xs">{CELL[s].label}</Text>
            </Group>
          ))}
        </Group>
      </Group>
      <Table.ScrollContainer minWidth={420}>
        <Table verticalSpacing={4} withRowBorders={false}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th />
              {schedule.days.map((d) => (
                <Table.Th key={d} ta="center">
                  <Text size="xs" fw={600}>
                    {shortDate(d)}
                  </Text>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {schedule.rows.map((row) => (
              <Table.Tr key={row.player_id}>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <Box style={{ whiteSpace: 'nowrap' }}>
                      <PlayerLink id={row.player_id}>{row.player}</PlayerLink>
                    </Box>
                    <StatusBadge status={row.status} />
                  </Group>
                </Table.Td>
                {row.cells.map((cell, i) => (
                  <Table.Td key={schedule.days[i]} ta="center">
                    {cell ? (
                      <Tooltip label={`${row.player} · ${shortDate(schedule.days[i])}: ${CELL[cell].label}`}>
                        <Box className={`${classes.cell} ${CELL[cell].className}`} />
                      </Tooltip>
                    ) : (
                      <Box className={classes.empty} />
                    )}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  )
}
