import { Alert, Button, Center, Loader, Stack, Text } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

interface Props<T> {
  query: UseQueryResult<T>
  children: (data: T) => ReactNode
  loadingLabel?: string
}

/** Uniform loading / error / data rendering for a React Query result. */
export function QueryState<T>({ query, children, loadingLabel = 'Pulling your league from ESPN…' }: Props<T>) {
  if (query.isPending) {
    return (
      <Center mih={240}>
        <Stack align="center" gap="xs">
          <Loader type="dots" size="lg" />
          <Text c="dimmed" size="sm">
            {loadingLabel}
          </Text>
        </Stack>
      </Center>
    )
  }
  if (query.isError) {
    return (
      <Alert color="red" variant="light" icon={<IconAlertTriangle />} title="Couldn't load this">
        <Stack gap="sm" align="flex-start">
          <Text size="sm">{query.error.message}</Text>
          <Button size="xs" variant="light" color="red" onClick={() => query.refetch()}>
            Try again
          </Button>
        </Stack>
      </Alert>
    )
  }
  return <>{children(query.data)}</>
}
