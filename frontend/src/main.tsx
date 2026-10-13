import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './design/base.css'
import { applyTheme, readTheme } from './design/theme'
import { toast } from './components/Toasts'
import { makeRouter } from './routes/router'

applyTheme(readTheme())
const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, retry: 1 } },
  // every action that fails says so, since its change on screen has just been undone
  mutationCache: new MutationCache({
    onError: (err, _vars, _ctx, mutation) => {
      const what = (mutation.meta as { failed?: string } | undefined)?.failed ?? "Couldn't save that"
      toast(`${what}: ${err instanceof Error ? err.message : String(err)}`, true)
    },
  }),
})
const router = makeRouter(queryClient)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
