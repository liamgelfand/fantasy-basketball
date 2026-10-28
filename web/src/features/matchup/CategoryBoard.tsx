import { Badge, Group, Paper, Progress, SimpleGrid, Stack, Text, Title, Tooltip } from '@mantine/core'
import type { CategoryOutlook } from '../../api/types'
import { formatStat, pct, probColor, probEmoji } from '../../lib/format'

export function CategoryBoard({ categories, punts }: { categories: CategoryOutlook[]; punts: string[] }) {
  return (
    <Paper>
      <Group justify="space-between" mb="md">
        <Title order={4}>Category battle</Title>
        <Text size="xs" c="dimmed">
          Now → projected final, with your odds of winning each
        </Text>
      </Group>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" verticalSpacing="sm">
        {categories.map((c) => (
          <CategoryRow key={c.stat} c={c} punted={punts.includes(c.stat)} />
        ))}
      </SimpleGrid>
    </Paper>
  )
}

function CategoryRow({ c, punted }: { c: CategoryOutlook; punted: boolean }) {
  const color = probColor(c.win_prob)
  return (
    <Stack gap={6} opacity={punted ? 0.5 : 1}>
      <Group justify="space-between" wrap="nowrap">
        <Group gap={6} wrap="nowrap">
          <Text fw={700} w={48}>
            {c.stat}
          </Text>
          {punted && (
            <Badge size="xs" variant="outline" color="gray">
              punt
            </Badge>
          )}
          <Text size="xs" c="dimmed" visibleFrom="xs">
            {formatStat(c.stat, c.mine_now)} – {formatStat(c.stat, c.theirs_now)} now
          </Text>
        </Group>
        <Group gap={6} wrap="nowrap">
          <Text size="sm" fw={600}>
            {formatStat(c.stat, c.mine_final)} <Text span c="dimmed">vs</Text> {formatStat(c.stat, c.theirs_final)}
          </Text>
          <Badge color={color} variant="light" w={64}>
            {pct(c.win_prob)}
          </Badge>
          <Text w={22} ta="center" aria-hidden>
            {probEmoji(c.win_prob)}
          </Text>
        </Group>
      </Group>
      <Tooltip label={`${pct(c.win_prob)} chance to win ${c.stat}`} position="top-start">
        <Progress value={c.win_prob * 100} color={color} size="md" radius="xl" animated={c.win_prob > 0.4 && c.win_prob < 0.6} />
      </Tooltip>
    </Stack>
  )
}
