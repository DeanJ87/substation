// Render the real app at a URL, signed in, against the fake API (005-DR-29).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createMemoryHistory, createRouter, RouterProvider } from '@tanstack/react-router'
import { render } from '@testing-library/react'
import { routeTree } from '../routes/router'
import { installFakeApi, type Overrides } from './fakeApi'

export async function renderRoute(url: string, overrides: Overrides = {}) {
  const api = installFakeApi(overrides)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history: createMemoryHistory({ initialEntries: [url] }),
  })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  await router.load()
  return { ...view, router, api, queryClient }
}
