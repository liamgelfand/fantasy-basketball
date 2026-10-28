import { ActionIcon, Group, Paper, Text, Textarea, Tooltip } from '@mantine/core'
import { IconArrowUp, IconPlayerStopFilled } from '@tabler/icons-react'
import { useState, type KeyboardEvent } from 'react'
import classes from './Chat.module.css'

interface Props {
  onSend: (text: string) => void
  onStop: () => void
  busy: boolean
  disabled: boolean
}

/** Pinned to the bottom of the chat page. Enter sends, Shift+Enter adds a new line. */
export function ChatComposer({ onSend, onStop, busy, disabled }: Props) {
  const [text, setText] = useState('')
  const canSend = !busy && !disabled && text.trim().length > 0

  const submit = () => {
    if (!canSend) return
    onSend(text)
    setText('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className={classes.composerBar}>
      <Paper className={classes.composer} p={6} shadow="sm">
        <Group gap={6} align="flex-end" wrap="nowrap">
          <Textarea
            aria-label="Message Claude"
            placeholder={disabled ? 'Claude is not configured' : 'Ask about your team…'}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            onKeyDown={onKeyDown}
            autosize
            minRows={1}
            maxRows={8}
            variant="unstyled"
            disabled={disabled}
            className={classes.input}
            autoFocus
          />
          {busy ? (
            <Tooltip label="Stop waiting">
              <ActionIcon size={38} radius="xl" variant="filled" color="gray" onClick={onStop} aria-label="Stop">
                <IconPlayerStopFilled size={16} />
              </ActionIcon>
            </Tooltip>
          ) : (
            <ActionIcon
              size={38}
              radius="xl"
              variant="gradient"
              gradient={{ from: 'court', to: 'grape' }}
              onClick={submit}
              disabled={!canSend}
              aria-label="Send"
            >
              <IconArrowUp size={20} stroke={2.5} />
            </ActionIcon>
          )}
        </Group>
      </Paper>
      <Text size="xs" c="dimmed" ta="center" mt={6}>
        Enter to send · Shift+Enter for a new line · Suggestions only: you make the moves in ESPN
      </Text>
    </div>
  )
}
