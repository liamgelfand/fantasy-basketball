import { Button, Center, Loader, Stack, Text, Title } from '@mantine/core'
import { lazy, Suspense, type ComponentType } from 'react'
import { Link, Route, Routes } from 'react-router'
import { AppLayout } from './components/AppLayout'

// Each page is its own chunk, so the first load only ships the page you land on.
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((m) => ({ default: m[name] })))
}

const MatchupPage = page(() => import('./features/matchup/MatchupPage'), 'MatchupPage')
const RosterPage = page(() => import('./features/roster/RosterPage'), 'RosterPage')
const FreeAgentsPage = page(() => import('./features/free-agents/FreeAgentsPage'), 'FreeAgentsPage')
const SimulatorPage = page(() => import('./features/simulator/SimulatorPage'), 'SimulatorPage')
const TradesPage = page(() => import('./features/trades/TradesPage'), 'TradesPage')
const LeaguePage = page(() => import('./features/league/LeaguePage'), 'LeaguePage')
const ChatPage = page(() => import('./features/chat/ChatPage'), 'ChatPage')
const ReportPage = page(() => import('./features/report/ReportPage'), 'ReportPage')

const routes: [string | undefined, ComponentType][] = [
  [undefined, MatchupPage],
  ['roster', RosterPage],
  ['free-agents', FreeAgentsPage],
  ['simulator', SimulatorPage],
  ['trades', TradesPage],
  ['league', LeaguePage],
  ['chat', ChatPage],
  ['report', ReportPage],
]

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        {routes.map(([path, Page]) => {
          const element = (
            <Suspense fallback={<PageLoader />}>
              <Page />
            </Suspense>
          )
          return path ? <Route key={path} path={path} element={element} /> : <Route key="index" index element={element} />
        })}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}

function PageLoader() {
  return (
    <Center mih={240}>
      <Loader type="dots" />
    </Center>
  )
}

function NotFound() {
  return (
    <Center mih={400}>
      <Stack align="center">
        <Text fz={64} aria-hidden>
          🧱
        </Text>
        <Title order={2}>Airball</Title>
        <Text c="dimmed">That page doesn't exist.</Text>
        <Button component={Link} to="/">
          Back to the matchup
        </Button>
      </Stack>
    </Center>
  )
}
