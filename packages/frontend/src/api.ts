import axios from 'axios'
import type {
  ApiEpisode,
  ApiEscalation,
  ApiPatient,
  Patient,
} from './types'
import { seedPatients } from './mockData'

// ============================================================================
//  ContinuaCare API client
//
//  Today the UI runs on local mock/seed data (VITE_USE_MOCK=true, the default).
//  When the backend is live, set VITE_USE_MOCK=false and point VITE_API_URL at
//  it, every call below switches from mock to a real HTTP request. No UI change.
// ============================================================================

export const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) || 'http://localhost:8000'

// Mock unless explicitly disabled.
export const USE_MOCK =
  (import.meta.env.VITE_USE_MOCK as string | undefined) !== 'false'

const api = axios.create({ baseURL: API_URL })
export default api

// ----------------------------------------------------------------------------
//  Typed endpoint helpers, exactly the endpoints in master spec §4 / §10.
//  Use these directly once the backend is up.
// ----------------------------------------------------------------------------

export const getPatients = () => api.get<ApiPatient[]>('/patients')
export const getPatient = (id: string) => api.get<ApiPatient>(`/patients/${id}`)
export const getPatientEpisode = (patientId: string) =>
  api.get<ApiEpisode>(`/patients/${patientId}/episode`)
export const getEpisode = (id: string) => api.get<ApiEpisode>(`/episodes/${id}`)
export const createEpisode = (body: {
  patient_id: string
  discharge_date: string
  discharge_notes: string
}) => api.post<ApiEpisode>('/episodes', body)
export const triggerCall = (episodeId: string) =>
  api.post(`/calls/trigger/${episodeId}`)
export const getOpenEscalations = () =>
  api.get<ApiEscalation[]>('/escalations/open')
export const acknowledgeAlert = (id: string) =>
  api.patch(`/escalations/${id}`, { status: 'resolved' })
export const generateBilling = (episodeId: string) =>
  api.post(`/episodes/${episodeId}/generate-billing`)
export const setEpisodeState = (episodeId: string, state: string) =>
  api.patch(`/episodes/${episodeId}/state`, { state })
export const fastForward = (episodeId: string) =>
  api.post(`/demo/fast-forward/${episodeId}`)

// ----------------------------------------------------------------------------
//  Adapter, fold a backend Patient + Episode into the console's view model.
//  Lossy on purpose: the console only needs what it renders. Extend as the
//  real API shape settles. (Transcript / call summary come from the Call rows.)
// ----------------------------------------------------------------------------

const COMPLEXITY_AMOUNT: Record<string, string> = {
  '99495': '$201.20',
  '99496': '$272.68',
}

export function toPatientVM(p: ApiPatient, ep?: ApiEpisode): Patient {
  const day = ep?.discharge_date
    ? Math.max(
        0,
        Math.round(
          (Date.parse('2026-06-27') - Date.parse(ep.discharge_date)) / 86_400_000
        )
      )
    : 0
  const code = ep?.cpt_code ?? null
  const confirmed = !!ep?.ready_to_bill || ep?.state === 'ready_to_bill'
  const escalated = ep?.state === 'escalated'
  return {
    id: p.id,
    name: p.name,
    age: p.age,
    sex: 'F',
    phone: p.phone,
    facility: '—',
    dischargeText: `Day ${day}`,
    dayLine: `Day ${day}`,
    day,
    dx: p.diagnosis,
    status: ep?.state ?? 'discharge_detected',
    statusKind: escalated
      ? 'flag'
      : ep?.state === 'ready_to_bill'
      ? 'ready'
      : code && !confirmed
      ? 'await'
      : 'window',
    contactDone: ep ? ep.state !== 'discharge_detected' && ep.state !== 'awaiting_call' : false,
    contactDay: 1,
    visit: ep?.face_to_face_date ? { slot: ep.face_to_face_date, provider: '' } : null,
    code,
    complexity: ep?.complexity === 'high' ? 'High complexity' : ep?.complexity === 'moderate' ? 'Moderate complexity' : null,
    codeAmount: code ? COMPLEXITY_AMOUNT[code] ?? null : null,
    codeRationale: ep?.triage_reason ?? null,
    codeConfirmed: confirmed,
    flag: escalated ? (ep?.triage_reason ?? 'Escalation raised, review required.') : null,
    ready: ep?.state === 'ready_to_bill',
    transcript: [],
  }
}

// ----------------------------------------------------------------------------
//  High-level loader the console calls on mount.
//  Mock mode → seed roster. Live mode → GET /patients (+ episodes) and adapt.
// ----------------------------------------------------------------------------

export async function getRoster(): Promise<Patient[]> {
  if (USE_MOCK) return seedPatients()

  const { data: patients } = await getPatients()
  // Pull each patient's most recent episode in parallel, then adapt.
  const episodes = await Promise.all(
    patients.map((p) =>
      getPatientEpisode(p.id)
        .then((r) => r.data)
        .catch(() => undefined)
    )
  )
  return patients.map((p, i) => toPatientVM(p, episodes[i]))
}
