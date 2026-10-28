import '@mantine/core/styles.css'
import '@mantine/charts/styles.css'
import '@mantine/notifications/styles.css'

import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { ApiError } from './api/client'
import { App } from './App'
import { ChatProvider } from './features/chat/ChatProvider'
import { SettingsProvider } from './state/settings'
import { theme } from './theme'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The server caches ESPN for 10 minutes; match it so tab switches are instant.
      staleTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status < 500),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <SettingsProvider>
          <ChatProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ChatProvider>
        </SettingsProvider>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
