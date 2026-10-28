import { Alert, Button, Group, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { IconSparkles } from '@tabler/icons-react'
import { useRef, useState } from 'react'
import { api } from '../../api/endpoints'
import { useMeta, useReport } from '../../api/queries'
import { Markdown } from '../../components/Markdown'
import { PageHeader } from '../../components/PageHeader'
import { QueryState } from '../../components/QueryState'
import { useSettings } from '../../state/useSettings'

type PlanState =
  | { status: 'idle' }
  | { status: 'running'; tools: string[] }
  | { status: 'done'; text: string }
  | { status: 'error'; message: string }

const PLAN_KEY = 'fantasy-hq:game-plan'

// The last finished plan is kept for this browser tab, so leaving the page doesn't discard it.
function loadPlan(): PlanState {
  try {
    const text = sessionStorage.getItem(PLAN_KEY)
    if (text) return { status: 'done', text }
  } catch {
    /* storage blocked */
  }
  return { status: 'idle' }
}

function savePlan(text: string) {
  try {
    sessionStorage.setItem(PLAN_KEY, text)
  } catch {
    /* non-essential */
  }
}

export function ReportPage() {
  const report = useReport()
  const meta = useMeta()
  const { params } = useSettings()
  const [plan, setPlan] = useState<PlanState>(loadPlan)
  const abort = useRef<AbortController | null>(null)

  const runPlan = async () => {
    abort.current = new AbortController()
    setPlan({ status: 'running', tools: [] })
    try {
      await api.gamePlan(
        params,
        (e) => {
          if (e.event === 'tool')
            setPlan((p) => (p.status === 'running' ? { ...p, tools: [...p.tools, e.data.label] } : p))
          else if (e.event === 'answer') {
            savePlan(e.data.text)
            setPlan({ status: 'done', text: e.data.text })
          }
          else setPlan({ status: 'error', message: e.data.message })
        },
        abort.current.signal,
      )
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') setPlan(loadPlan())
      else setPlan({ status: 'error', message: err instanceof Error ? err.message : String(err) })
    }
  }

  // Closing the stream makes the server stop Claude before its next API call.
  const stopPlan = () => abort.current?.abort()

  return (
    <Stack gap="lg">
      <PageHeader
        title="Report"
        subtitle="Everything in one place, plus an AI-written game plan"
        right={
          <Button
            leftSection={<IconSparkles size={18} />}
            variant="gradient"
            gradient={{ from: 'court', to: 'grape' }}
            onClick={runPlan}
            loading={plan.status === 'running'}
            disabled={!meta.data?.chat_enabled}
            title={meta.data?.chat_enabled ? 'Uses API credits' : 'Add ANTHROPIC_API_KEY to .env to enable'}
          >
            Claude game plan
          </Button>
        }
      />

      {plan.status === 'running' && (
        <Paper>
          <Group justify="space-between">
            <Group gap="sm">
              <Loader size="sm" type="dots" />
              <Text fw={600}>Claude is building your game plan… this can take a few minutes</Text>
            </Group>
            <Button size="xs" variant="default" onClick={stopPlan}>
              Stop
            </Button>
          </Group>
          {plan.tools.length > 0 && (
            <Text size="xs" c="dimmed" mt="xs">
              {plan.tools.length} lookups · latest: {plan.tools[plan.tools.length - 1]}
            </Text>
          )}
        </Paper>
      )}
      {plan.status === 'error' && (
        <Alert color="red" variant="light" title="Game plan failed">
          {plan.message}
        </Alert>
      )}
      {plan.status === 'done' && (
        <Paper style={{ borderColor: 'var(--mantine-color-grape-4)' }}>
          <Group gap="xs" mb="sm">
            <IconSparkles size={18} color="var(--mantine-color-grape-6)" />
            <Title order={4}>Game plan</Title>
          </Group>
          <Markdown>{plan.text}</Markdown>
        </Paper>
      )}

      <Paper>
        <QueryState query={report}>{(r) => <Markdown>{r.markdown}</Markdown>}</QueryState>
      </Paper>
    </Stack>
  )
}
