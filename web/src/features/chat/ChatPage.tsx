import { Alert, Button, Center, Group, ScrollArea, SimpleGrid, Stack, Text, ThemeIcon, Title, UnstyledButton } from '@mantine/core'
import { IconMessageChatbot, IconPlus } from '@tabler/icons-react'
import { useEffect, useRef } from 'react'
import { useMeta } from '../../api/queries'
import classes from './Chat.module.css'
import { ChatComposer } from './ChatComposer'
import { ChatMessage } from './ChatMessage'
import { useChat } from './useChat'

const SUGGESTIONS = [
  { emoji: '🛒', text: 'Who should I pick up this week and who do I drop?' },
  { emoji: '🩹', text: 'Any injury news I should act on?' },
  { emoji: '🤝', text: 'Find me a trade that fixes my weakest spot.' },
  { emoji: '📈', text: 'Which categories should I chase or concede this week?' },
]

export function ChatPage() {
  const meta = useMeta()
  const { turns, busy, send, reset, stop } = useChat()
  const viewport = useRef<HTMLDivElement>(null)
  const last = turns[turns.length - 1]

  // Follow the conversation: keep the newest message (and live tool progress) in view.
  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' })
  }, [turns.length, last?.tools.length, last?.text])

  const disabled = meta.data ? !meta.data.chat_enabled : true

  return (
    <div className={classes.page}>
      <Group justify="space-between" px="lg" py="sm" className={classes.toolbar}>
        <Group gap="xs">
          <ThemeIcon variant="gradient" gradient={{ from: 'court', to: 'grape' }} radius="md">
            <IconMessageChatbot size={18} />
          </ThemeIcon>
          <div>
            <Text fw={700} size="sm">
              Ask Claude
            </Text>
            <Text size="xs" c="dimmed">
              Reads your live league, simulates moves, checks the news{meta.data && ` · ${meta.data.model}`}
            </Text>
          </div>
        </Group>
        <Button variant="default" size="xs" leftSection={<IconPlus size={14} />} onClick={reset} disabled={!turns.length}>
          New chat
        </Button>
      </Group>

      <ScrollArea className={classes.messages} viewportRef={viewport} type="auto" offsetScrollbars>
        <Stack className={classes.thread} gap="lg">
          {meta.data && !meta.data.chat_enabled && (
            <Alert color="yellow" variant="light" title="Claude isn't set up">
              Add ANTHROPIC_API_KEY to your .env file, then restart the server.
            </Alert>
          )}
          {turns.length === 0 ? (
            <Center className={classes.empty}>
              <Stack align="center" gap="lg" maw={640}>
                <Text fz={56} className={classes.wave} aria-hidden>
                  🏀
                </Text>
                <Title order={2} ta="center">
                  What's the play, coach?
                </Title>
                <Text c="dimmed" ta="center">
                  Ask anything about your team. Claude pulls rosters, projections, free agents and news before answering.
                </Text>
                <SimpleGrid cols={{ base: 1, sm: 2 }} w="100%">
                  {SUGGESTIONS.map((s) => (
                    <UnstyledButton
                      key={s.text}
                      className={classes.suggestion}
                      onClick={() => send(s.text)}
                      disabled={disabled}
                    >
                      <Text span mr={8} aria-hidden>
                        {s.emoji}
                      </Text>
                      <Text span size="sm">
                        {s.text}
                      </Text>
                    </UnstyledButton>
                  ))}
                </SimpleGrid>
              </Stack>
            </Center>
          ) : (
            turns.map((t) => <ChatMessage key={t.id} turn={t} />)
          )}
        </Stack>
      </ScrollArea>

      <ChatComposer onSend={send} onStop={stop} busy={busy} disabled={disabled} />
    </div>
  )
}
