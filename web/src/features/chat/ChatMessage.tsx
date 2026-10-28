import { Avatar, Box, Collapse, Divider, Group, Loader, Stack, Text, UnstyledButton } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconChevronDown, IconChevronRight, IconDatabaseSearch } from '@tabler/icons-react'
import { Markdown } from '../../components/Markdown'
import classes from './Chat.module.css'
import type { ChatTurn } from './useChat'

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  if (turn.role === 'notice') {
    return (
      <Divider
        label={
          <Text size="xs" c="dimmed">
            {turn.text}
          </Text>
        }
        labelPosition="center"
      />
    )
  }
  if (turn.role === 'user') {
    return (
      <Group justify="flex-end">
        <Box className={classes.userBubble}>
          <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
            {turn.text}
          </Text>
        </Box>
      </Group>
    )
  }

  return (
    <Group align="flex-start" gap="sm" wrap="nowrap">
      <Avatar radius="xl" variant="gradient" gradient={{ from: 'court', to: 'grape' }} size={34}>
        🏀
      </Avatar>
      <Stack gap={6} className={classes.assistant}>
        <ToolTrail tools={turn.tools} pending={turn.status === 'pending'} />
        {turn.status === 'pending' && !turn.text ? null : turn.status === 'error' ? (
          <Text size="sm" c="red">
            {turn.text}
          </Text>
        ) : (
          <Markdown>{turn.text}</Markdown>
        )}
      </Stack>
    </Group>
  )
}

function ToolTrail({ tools, pending }: { tools: string[]; pending: boolean }) {
  const [opened, { toggle }] = useDisclosure(false)
  if (!pending && !tools.length) return null
  const Chevron = opened ? IconChevronDown : IconChevronRight
  const latest = tools[tools.length - 1]

  return (
    <Box>
      <UnstyledButton onClick={toggle} disabled={!tools.length} className={classes.toolToggle}>
        <Group gap={6} wrap="nowrap">
          {pending ? <Loader size={14} type="oval" /> : <IconDatabaseSearch size={14} />}
          <Text size="xs" c="dimmed" fw={500}>
            {pending
              ? latest
                ? `Checking ${latest}…`
                : 'Thinking…'
              : `Looked at ${tools.length} data source${tools.length === 1 ? '' : 's'}`}
          </Text>
          {tools.length > 0 && <Chevron size={12} color="var(--mantine-color-dimmed)" />}
        </Group>
      </UnstyledButton>
      <Collapse expanded={opened}>
        <Stack gap={2} mt={6} pl="md" className={classes.toolList}>
          {tools.map((t, i) => (
            <Text key={i} size="xs" c="dimmed" ff="monospace">
              {t}
            </Text>
          ))}
        </Stack>
      </Collapse>
    </Box>
  )
}
