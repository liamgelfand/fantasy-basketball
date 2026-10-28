import { Text, type TextProps } from '@mantine/core'
import { IconArrowDownRight, IconArrowUpRight } from '@tabler/icons-react'
import type { ReactNode } from 'react'

/** A signed change, green when it helps you and red when it hurts. */
export function Delta({ value, children, ...props }: { value: number; children: ReactNode } & TextProps) {
  const color = value > 0 ? 'teal' : value < 0 ? 'red' : 'dimmed'
  const Icon = value >= 0 ? IconArrowUpRight : IconArrowDownRight
  return (
    <Text component="span" c={color} fw={600} size="sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }} {...props}>
      {value !== 0 && <Icon size={14} stroke={2.5} />}
      {children}
    </Text>
  )
}
