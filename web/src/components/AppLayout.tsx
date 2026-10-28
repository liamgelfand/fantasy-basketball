import {
  ActionIcon,
  Alert,
  AppShell,
  Avatar,
  Badge,
  Burger,
  Divider,
  Group,
  NavLink,
  Paper,
  ScrollArea,
  Skeleton,
  Stack,
  Text,
  Title,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { IconMoon, IconPlugConnectedX, IconRefresh, IconSun } from '@tabler/icons-react'
import { useEffect } from 'react'
import { NavLink as RouterLink, Outlet, useLocation } from 'react-router'
import { ApiError } from '../api/client'
import { useMeta, useRefresh } from '../api/queries'
import { titleCase } from '../lib/format'
import { NAV } from '../nav'
import { useSettings } from '../state/useSettings'
import classes from './AppLayout.module.css'
import { SettingsPanel } from './SettingsPanel'

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure()
  const location = useLocation()
  const meta = useMeta()
  const refresh = useRefresh()
  const { setColorScheme } = useMantineColorScheme()
  const scheme = useComputedColorScheme('light')
  const isChat = location.pathname === '/chat'
  const { params, reset } = useSettings()

  // Settings saved in this browser can go stale (e.g. a window the server no longer accepts):
  // fall back to the server defaults instead of failing every page.
  const staleSettings = meta.error instanceof ApiError && meta.error.status === 422
  useEffect(() => {
    if (staleSettings && (params.window !== null || params.punts !== null)) reset()
  }, [staleSettings, params, reset])

  const onRefresh = () =>
    refresh.mutate(undefined, {
      onSuccess: () => notifications.show({ message: 'Pulling fresh data from ESPN 🏀', color: 'court' }),
      onError: (e) => notifications.show({ title: 'Refresh failed', message: e.message, color: 'red' }),
    })

  const loadedAt = meta.data
    ? new Date(meta.data.loaded_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : null

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 280, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding={isChat ? 0 : 'lg'}
    >
      <AppShell.Header className={classes.header}>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <Text className={classes.ball} aria-hidden>
              🏀
            </Text>
            <Title order={3} className={classes.brand}>
              Fantasy HQ
            </Title>
            {meta.data && (
              <Badge variant="light" color="gray" visibleFrom="md">
                {meta.data.name}
              </Badge>
            )}
          </Group>
          <Group gap="xs" wrap="nowrap">
            {loadedAt && (
              <Text size="xs" c="dimmed" visibleFrom="sm">
                Data as of {loadedAt}
              </Text>
            )}
            <Tooltip label="Refresh from ESPN">
              <ActionIcon
                variant="default"
                size="lg"
                onClick={onRefresh}
                loading={refresh.isPending}
                aria-label="Refresh from ESPN"
              >
                <IconRefresh size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label={scheme === 'dark' ? 'Light mode' : 'Dark mode'}>
              <ActionIcon
                variant="default"
                size="lg"
                onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
                aria-label="Toggle color scheme"
              >
                {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar>
        <AppShell.Section p="md">
          {meta.data ? (
            <Paper p="sm" className={classes.teamCard}>
              <Group gap="sm" wrap="nowrap">
                <Avatar color="court" radius="md" variant="filled">
                  {meta.data.my_team.abbrev.slice(0, 3)}
                </Avatar>
                <div style={{ minWidth: 0 }}>
                  <Text fw={700} truncate>
                    {meta.data.my_team.name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {meta.data.my_team.record} · #{meta.data.my_team.standing} of {meta.data.teams.length} ·{' '}
                    {titleCase(meta.data.scoring_type)}
                  </Text>
                </div>
              </Group>
            </Paper>
          ) : (
            <Skeleton h={62} radius="lg" />
          )}
        </AppShell.Section>

        <AppShell.Section grow component={ScrollArea} px="sm">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              component={RouterLink}
              to={item.path}
              end={item.path === '/'}
              label={item.label}
              description={item.description}
              leftSection={<item.icon size={20} stroke={1.6} />}
              onClick={close}
              className={classes.navLink}
            />
          ))}
        </AppShell.Section>

        <AppShell.Section p="md">
          <Divider mb="md" />
          {meta.data ? <SettingsPanel meta={meta.data} /> : <Skeleton h={120} />}
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main className={isChat ? classes.mainChat : undefined}>
        {meta.isError && !staleSettings && (
          <Alert
            color="red"
            variant="light"
            icon={<IconPlugConnectedX />}
            title="Can't reach your league"
            mb={isChat ? 0 : 'lg'}
            m={isChat ? 'md' : undefined}
          >
            <Text size="sm">{meta.error.message}</Text>
            <Text size="xs" c="dimmed" mt={4}>
              If ESPN returns 401, your espn_s2 / SWID cookies expired: copy fresh ones into .env and restart.
            </Text>
          </Alert>
        )}
        {isChat ? (
          <Outlet />
        ) : (
          <Stack maw={1280} mx="auto" gap={0}>
            <Outlet />
          </Stack>
        )}
      </AppShell.Main>
    </AppShell>
  )
}
