import { Box, Group, Stack, Text, Tooltip } from '@mantine/core'
import classes from './DeltaBars.module.css'

export interface DeltaRow {
  stat: string
  value: number
}

interface Props {
  rows: DeltaRow[]
  format: (value: number, stat: string) => string
  /** Stats where a decrease helps you (e.g. TO for raw stat changes; not for win-odds changes). */
  reverse?: string[]
}

/**
 * Diverging bars around zero, colored by whether the change helps you: with TO in `reverse`,
 * more turnovers shows red even though the number went up.
 */
export function DeltaBars({ rows, format, reverse = [] }: Props) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-9)
  return (
    <Stack gap={6}>
      {rows.map((r) => {
        const lowerIsBetter = reverse.includes(r.stat)
        const good = lowerIsBetter ? r.value < 0 : r.value > 0
        const tone = r.value === 0 ? classes.neutral : good ? classes.good : classes.bad
        const textColor = r.value === 0 ? 'dimmed' : good ? 'teal.7' : 'red.7'
        const width = `${(Math.abs(r.value) / max) * 50}%`
        return (
          <Group key={r.stat} gap="sm" wrap="nowrap">
            <Text size="sm" fw={600} w={56} ta="right">
              {r.stat}
            </Text>
            <Tooltip label={`${r.stat}: ${format(r.value, r.stat)}${lowerIsBetter ? ' (lower is better)' : ''}`}>
              <Box className={classes.track}>
                <Box className={classes.axis} />
                <Box
                  className={`${classes.bar} ${tone}`}
                  style={r.value >= 0 ? { left: '50%', width } : { right: '50%', width }}
                />
              </Box>
            </Tooltip>
            <Text size="sm" w={64} fw={600} c={textColor}>
              {format(r.value, r.stat)}
            </Text>
          </Group>
        )
      })}
    </Stack>
  )
}
