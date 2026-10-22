// The trail on a dataset leads back up: Library / Collections / its collection / its project (owner 2026-10-22).
import { cleanup, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fakeFor } from '../../test/fakeApi'
import { renderRoute } from '../../test/renderRoute'

afterEach(cleanup)

const base = fakeFor('get', '/datasets/{id}')

describe('dataset breadcrumbs', () => {
  it('link to the collection and the project', async () => {
    await renderRoute('/datasets/1', {
      'GET /datasets/1': {
        ...base,
        id: 1,
        collection_id: 4,
        collection: 'Flame Nebula',
        project_id: 13,
        project_label: '2025',
      },
    })
    const trail = (await screen.findByRole('link', { name: 'Flame Nebula' })).parentElement!
    expect(within(trail).getByRole('link', { name: 'Collections' })).toHaveAttribute(
      'href',
      '/#library-collections-h',
    )
    expect(within(trail).getByRole('link', { name: 'Flame Nebula' })).toHaveAttribute(
      'href',
      '/collections/4',
    )
    expect(within(trail).getByRole('link', { name: '2025' })).toHaveAttribute(
      'href',
      '/collections/4?project=13',
    )
  })

  it('lead to "Not in a collection" when it has none', async () => {
    await renderRoute('/datasets/1', {
      'GET /datasets/1': { ...base, id: 1, collection_id: null, collection: null, project_id: null },
    })
    expect(await screen.findByRole('link', { name: 'Not in a collection' })).toHaveAttribute(
      'href',
      '/#library-ungrouped-h',
    )
  })
})
