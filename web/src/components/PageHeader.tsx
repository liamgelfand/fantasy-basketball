import { Group, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

export function PageHeader({ title, subtitle, right }: { title: ReactNode; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg" gap="sm">
      <div>
        <Title order={2}>{title}</Title>
        {subtitle && (
          <Text c="dimmed" size="sm" mt={4}>
            {subtitle}
          </Text>
        )}
      </div>
      {right}
    </Group>
  )
}
