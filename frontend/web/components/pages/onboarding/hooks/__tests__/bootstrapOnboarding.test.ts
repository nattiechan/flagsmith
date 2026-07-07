import { bootstrapOnboarding } from 'components/pages/onboarding/hooks/bootstrapOnboarding'
import API from 'project/api'
import Constants from 'common/constants'
import { getEnvironments } from 'common/services/useEnvironment'
import { createOrganisationViaAccountStore } from 'components/pages/onboarding/hooks/createOrganisationViaAccountStore'

// bootstrapOnboarding orchestrates RTK dispatches + the account store. We only
// care here about which analytics milestones it emits, so mock the plumbing:
// each endpoint's initiate() returns a `{ __t }` marker, and the fake store's
// dispatch maps that marker to a canned result.
jest.mock('project/api', () => ({
  __esModule: true,
  default: { trackEvent: jest.fn() },
}))
jest.mock('common/store', () => ({ getStore: jest.fn() }))
// Real Constants pulls in utils -> account-store (untransformed ESM). Mock the
// events the bootstrap emits; the code and the assertions share this mock.
jest.mock('common/constants', () => ({
  __esModule: true,
  default: {
    events: {
      CREATE_FEATURE: { category: 'Features', event: 'Feature created' },
      CREATE_FIRST_FEATURE: {
        category: 'First',
        event: 'First Feature created',
      },
      CREATE_FIRST_PROJECT: {
        category: 'First',
        event: 'First Project created',
      },
      CREATE_PROJECT: { category: 'Project', event: 'Project created' },
    },
  },
}))
jest.mock('common/dispatcher/app-actions', () => ({
  __esModule: true,
  default: { refreshOrganisation: jest.fn(), selectOrganisation: jest.fn() },
}))
jest.mock(
  'components/pages/onboarding/hooks/createOrganisationViaAccountStore',
  () => ({ createOrganisationViaAccountStore: jest.fn() }),
)
jest.mock('common/services/useOrganisation', () => ({
  organisationService: {
    util: { invalidateTags: () => ({ __t: 'invalidateOrg' }) },
  },
}))
jest.mock('common/services/useProject', () => ({
  projectService: {
    endpoints: {
      createProject: { initiate: () => ({ __t: 'createProject' }) },
      getProjects: { initiate: () => ({ __t: 'getProjects' }) },
    },
  },
}))
jest.mock('common/services/useEnvironment', () => ({
  __esModule: true,
  environmentService: {
    endpoints: {
      createEnvironment: { initiate: () => ({ __t: 'createEnvironment' }) },
    },
  },
  getEnvironments: jest.fn(),
}))
jest.mock('common/services/useProjectFlag', () => ({
  projectFlagService: {
    endpoints: {
      createProjectFlag: { initiate: () => ({ __t: 'createProjectFlag' }) },
      getProjectFlags: { initiate: () => ({ __t: 'getProjectFlags' }) },
      updateProjectFlag: { initiate: () => ({ __t: 'updateProjectFlag' }) },
    },
  },
}))
jest.mock('common/services/useTag', () => ({
  tagService: {
    endpoints: {
      createTag: { initiate: () => ({ __t: 'createTag' }) },
      getTags: { initiate: () => ({ __t: 'getTags' }) },
    },
  },
}))

const trackEvent = API.trackEvent as jest.Mock
const getEnvironmentsMock = getEnvironments as jest.Mock
const createOrg = createOrganisationViaAccountStore as jest.Mock

const DEV_ENV = { api_key: 'abc', id: 10, name: 'Development' }
const defaults = { orgName: 'My organisation', projectName: 'My first project' }

const makeStore = (results: Record<string, unknown>) =>
  ({
    dispatch: jest.fn((action: { __t?: string }) => ({
      unwrap: () => Promise.resolve(results[action?.__t ?? '']),
    })),
  } as never)

const emitted = (event: string) =>
  trackEvent.mock.calls.some(([arg]) => arg?.event === event)

beforeEach(() => {
  jest.clearAllMocks()
  createOrg.mockResolvedValue(1)
  getEnvironmentsMock.mockResolvedValue({ data: { results: [DEV_ENV] } })
})

describe('bootstrapOnboarding analytics', () => {
  it('emits the First milestones (not the generic events) on a fresh create', async () => {
    const store = makeStore({
      createEnvironment: DEV_ENV,
      createProject: { id: 5, name: 'My first project' },
      createProjectFlag: { id: 9, name: 'show_demo_button', tags: [] },
      createTag: { id: 3, label: 'Onboarding' },
      getProjectFlags: { results: [] },
      getProjects: [],
      getTags: [],
    })

    await bootstrapOnboarding(store, { defaults })

    expect(emitted(Constants.events.CREATE_FIRST_PROJECT.event)).toBe(true)
    expect(emitted(Constants.events.CREATE_FIRST_FEATURE.event)).toBe(true)
    // Auto-creates must not fire the generic action events.
    expect(emitted(Constants.events.CREATE_PROJECT.event)).toBe(false)
    expect(emitted(Constants.events.CREATE_FEATURE.event)).toBe(false)
  })

  it('emits nothing when the project and flag are reused', async () => {
    const store = makeStore({
      getProjectFlags: {
        results: [{ id: 9, name: 'show_demo_button', tags: [] }],
      },
      getProjects: [{ id: 5, name: 'Existing' }],
      getTags: [],
      updateProjectFlag: {},
    })

    await bootstrapOnboarding(store, {
      defaults,
      existingOrg: { id: 1, name: 'Org' },
    })

    expect(emitted(Constants.events.CREATE_FIRST_PROJECT.event)).toBe(false)
    expect(emitted(Constants.events.CREATE_FIRST_FEATURE.event)).toBe(false)
  })

  it('does not emit First Feature when the project already has flags', async () => {
    const store = makeStore({
      createEnvironment: DEV_ENV,
      createProject: { id: 5, name: 'My first project' },
      createProjectFlag: { id: 9, name: 'show_demo_button', tags: [] },
      createTag: { id: 3, label: 'Onboarding' },
      // A non-onboarding flag exists, so the demo flag is created but is not
      // the user's first feature.
      getProjectFlags: { results: [{ id: 1, name: 'other_flag', tags: [] }] },
      getProjects: [],
      getTags: [],
      updateProjectFlag: {},
    })

    await bootstrapOnboarding(store, { defaults })

    expect(emitted(Constants.events.CREATE_FIRST_PROJECT.event)).toBe(true)
    expect(emitted(Constants.events.CREATE_FIRST_FEATURE.event)).toBe(false)
  })
})
