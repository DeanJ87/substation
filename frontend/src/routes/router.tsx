import { QueryClient } from '@tanstack/react-query'
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
} from '@tanstack/react-router'
import { getSession, type SessionUser } from '../api/auth'
import { Activity } from '../features/activity/Activity'
import { DatasetScreen } from '../features/dataset/DatasetScreen'
import { CollectionView } from '../features/library/CollectionView'
import { Library } from '../features/library/Library'
import { ReviewScreen } from '../features/review/ReviewScreen'
import { SubDetail } from '../features/sub/SubDetail'
import { NightView } from '../features/datasets/NightView'
import { ReconciliationList } from '../features/reconciliation/ReconciliationList'
import { CalibrationLibrary } from '../features/calibration/CalibrationLibrary'
import { CalibrationSetView } from '../features/calibration/CalibrationSetView'
import { ToShoot } from '../features/calibration/ToShoot'
import { readScope, type Scope } from '../features/scope/scope'
import { SettingsPage } from '../features/settings/SettingsPage'
import { BinPage } from '../features/bin/BinPage'
import { MapView } from '../features/map/MapView'
import { mapSearch } from '../features/map/search'
import { AppFrame } from './AppFrame'
import { SignIn } from './SignIn'

interface Ctx {
  queryClient: QueryClient
}

const root = createRootRouteWithContext<Ctx>()({ component: Outlet })

const signIn = createRoute({ getParentRoute: () => root, path: '/sign-in', component: SignIn })

const app = createRoute({
  getParentRoute: () => root,
  id: 'app',
  beforeLoad: async ({ context }) => {
    const user = await context.queryClient.ensureQueryData({ queryKey: ['session'], queryFn: getSession })
    if (!user) throw redirect({ to: '/sign-in' })
    return { user }
  },
  component: function App() {
    const { user } = app.useRouteContext() as { user: SessionUser }
    return <AppFrame user={user} />
  },
})

const datasets = createRoute({
  getParentRoute: () => app,
  path: '/',
  component: Library,
  validateSearch: (q: Record<string, unknown>): Scope => readScope(q), // spec 018
})
const collection = createRoute({
  getParentRoute: () => app,
  path: '/collections/$id',
  component: CollectionView,
  validateSearch: (
    q: Record<string, unknown>,
  ): Scope & {
    tab?: 'overview' | 'datasets' | 'sessions' | 'masters'
    nights?: string // only these nights (comma-separated): the sessions shot at one place, from the map (spec 012)
    at?: string // "lat,lon" of that place, to name it
  } => ({
    ...readScope(q), // carried from the Library or the map (spec 018)
    tab: ['overview', 'datasets', 'sessions', 'masters'].includes(String(q.tab))
      ? (q.tab as 'overview')
      : undefined,
    nights: typeof q.nights === 'string' && /^[\d,-]+$/.test(q.nights) ? q.nights : undefined,
    at: typeof q.at === 'string' && /^-?[\d.]+,-?[\d.]+$/.test(q.at) ? q.at : undefined,
  }),
})
const binRoute = createRoute({ getParentRoute: () => app, path: '/bin', component: BinPage })
const mapRoute = createRoute({
  getParentRoute: () => app,
  path: '/map',
  component: MapView,
  validateSearch: mapSearch, // where to look and which nights (spec 015)
})
const sub = createRoute({ getParentRoute: () => app, path: '/subs/$sha', component: SubDetail })
const activity = createRoute({ getParentRoute: () => app, path: '/activity', component: Activity })
const dataset = createRoute({
  getParentRoute: () => app,
  path: '/datasets/$id',
  component: DatasetScreen,
  validateSearch: (
    q: Record<string, unknown>,
  ): {
    tab?: 'subs' | 'quality' | 'calibration' | 'masters' | 'sky'
    night?: string
    sub?: string // the viewer is open on this sub (spec 012)
    show?: 'flagged' // the subs grid shows only flagged subs: what Review was (spec 012)
  } => ({
    tab: ['subs', 'quality', 'calibration', 'masters', 'sky'].includes(String(q.tab))
      ? (q.tab as 'subs')
      : undefined,
    night: typeof q.night === 'string' ? q.night : undefined,
    sub: typeof q.sub === 'string' && /^[0-9a-f]{64}$/.test(q.sub) ? q.sub : undefined,
    show: q.show === 'flagged' ? 'flagged' : undefined,
  }),
})
const nightRoute = createRoute({
  getParentRoute: () => app,
  path: '/nights/$date',
  component: NightView,
  validateSearch: (q: Record<string, unknown>): Scope & { site?: string; sub?: string } => ({
    ...readScope(q), // carried from the map or a collection (spec 018)
    site: typeof q.site === 'string' && q.site ? q.site : undefined, // which place, when several shot that night
    sub: typeof q.sub === 'string' && /^[0-9a-f]{64}$/.test(q.sub) ? q.sub : undefined, // the viewer (spec 012)
  }),
})
const review = createRoute({
  getParentRoute: () => app,
  path: '/review',
  component: ReviewScreen,
  validateSearch: (q: Record<string, unknown>): { dataset?: number } => ({
    dataset: Number.isFinite(Number(q.dataset)) && q.dataset != null ? Number(q.dataset) : undefined,
  }),
})
const calibration = createRoute({
  getParentRoute: () => app,
  path: '/calibration',
  component: CalibrationLibrary,
  validateSearch: (q: Record<string, unknown>): Scope => readScope(q), // spec 018
})
const calibrationToShoot = createRoute({
  getParentRoute: () => app,
  path: '/calibration/to-shoot',
  component: ToShoot,
  validateSearch: (q: Record<string, unknown>): Scope => readScope(q), // spec 018
})
const calibrationSet = createRoute({
  getParentRoute: () => app,
  path: '/calibration/sets/$id',
  component: CalibrationSetView,
})
const settings = createRoute({ getParentRoute: () => app, path: '/settings', component: SettingsPage })
// the old queue page: Activity is the one queue screen now (005-DR-01)
const queue = createRoute({
  getParentRoute: () => app,
  path: '/queue',
  beforeLoad: () => {
    throw redirect({ to: '/activity' })
  },
})
const reconcile = createRoute({
  getParentRoute: () => app,
  path: '/reconcile',
  component: ReconciliationList,
})

export const routeTree = root.addChildren([
  signIn,
  app.addChildren([
    mapRoute,
    binRoute,
    datasets,
    collection,
    dataset,
    sub,
    nightRoute,
    reconcile,
    queue,
    activity,
    review,
    calibration,
    calibrationSet,
    calibrationToShoot,
    settings,
  ]),
])

export function makeRouter(queryClient: QueryClient) {
  return createRouter({ routeTree, context: { queryClient }, defaultPreload: 'intent' })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof makeRouter>
  }
}
