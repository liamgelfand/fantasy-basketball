import { Group, Paper, Text, ThemeIcon } from '@mantine/core'
import type { ReactNode } from 'react'
import classes from './StatCard.module.css'

interface Props {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  color?: string
}

export function StatCard({ label, value, hint, icon, color = 'court' }: Props) {
  return (
    <Paper className={classes.card}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text size="xs" tt="uppercase" fw={700} c="dimmed" lts={0.5}>
            {label}
          </Text>
          <Text className={classes.value}>{value}</Text>
          {hint && (
            <Text size="sm" c="dimmed" mt={4}>
              {hint}
            </Text>
          )}
        </div>
        {icon && (
          <ThemeIcon size={44} radius="md" variant="light" color={color}>
            {icon}
          </ThemeIcon>
        )}
      </Group>
    </Paper>
  )
}
