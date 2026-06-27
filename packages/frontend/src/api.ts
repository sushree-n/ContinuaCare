import axios from 'axios'
import type {
  ApiCall,
  ApiEpisode,
  ApiEscalation,
  ApiPatient,
  Patient,
  TranscriptLine,
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
export const getCallsForEpisode = (episodeId: string) =>
  api.get<ApiCall[]>(`/calls/episode/${episodeId}`)
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

function parseTranscript(raw: string | undefined | null, _patientName: string): TranscriptLine[] {
  if (!raw) return []
  const result: TranscriptLine[] = []
  for (const line of raw.split('\n')) {
    const cleaned = line.replace(/^\[['"]|['"]\]$/g, '').trim()
    if (!cleaned) continue
    const agentMatch = cleaned.match(/^(Agent|Aria|ContinuaCare|assistant):\s*(.+)/i)
    const patientMatch = cleaned.match(/^(Patient|user):\s*(.+)/i)
    if (agentMatch) {
      result.push({ who: 'agent', text: agentMatch[2] })
    } else if (patientMatch) {
      const text = patientMatch[2].replace(/^\[['"]|['"]\]$/g, '').trim()
      if (text) result.push({ who: 'patient', text })
    } else {
      result.push({ who: 'agent', text: cleaned })
    }
  }
  return result
}

export function toPatientVM(p: ApiPatient, ep?: ApiEpisode, calls?: ApiCall[]): Patient {
  const day = ep?.discharge_date
    ? Math.max(
        0,
        Math.round(
          (Date.now() - Date.parse(ep.discharge_date)) / 86_400_000
        )
      )
    : 0
  const code = ep?.cpt_code ?? null
  const confirmed = !!ep?.ready_to_bill || ep?.state === 'ready_to_bill'
  const escalated = ep?.state === 'escalated'
  const hasEpisode = !!ep

  let statusKind: Patient['statusKind'] = 'new'
  if (!hasEpisode) statusKind = 'new'
  else if (escalated) statusKind = 'flag'
  else if (ep?.state === 'ready_to_bill') statusKind = 'ready'
  else if (ep?.state === 'call_in_progress') statusKind = 'calling'
  else if (code && !confirmed) statusKind = 'await'
  else statusKind = 'window'

  const meds = Array.isArray(p.medications) ? p.medications : []

  // Use the most recent completed call for transcript/summary
  const completedCall = (calls ?? [])
    .filter((c) => c.status === 'completed')
    .sort((a, b) => (b.attempt_number ?? 0) - (a.attempt_number ?? 0))[0]
  const transcript = parseTranscript(completedCall?.transcript, p.name)

  return {
    id: p.id,
    name: p.name,
    age: p.age,
    sex: 'F',
    phone: p.phone,
    facility: '—',
    dischargeText: ep ? `Day ${day}` : '—',
    dayLine: ep ? `Day ${day}` : '—',
    day,
    dx: p.diagnosis,
    discharge_notes: ep?.discharge_notes,
    medications: meds,
    episodeId: ep?.id,
    status: ep?.state ?? '',
    statusKind,
    hasEpisode,
    contactDone: ep
      ? !['discharge_detected', 'awaiting_call', 'call_in_progress'].includes(ep.state)
      : false,
    contactDay: 1,
    visit: ep?.face_to_face_date ? { slot: new Date(ep.face_to_face_date).toLocaleDateString(), provider: '' } : null,
    code,
    complexity: ep?.complexity === 'high' ? 'High complexity' : ep?.complexity === 'moderate' ? 'Moderate complexity' : null,
    codeAmount: code ? COMPLEXITY_AMOUNT[code] ?? null : null,
    codeRationale: ep?.triage_reason ?? ep?.triage_rationale ?? null,
    codeConfirmed: confirmed,
    flag: escalated ? (ep?.triage_reason ?? ep?.triage_rationale ?? 'Escalation raised, review required.') : null,
    ready: ep?.state === 'ready_to_bill',
    callSummary: completedCall?.summary ?? undefined,
    transcript,
  }
}

// ----------------------------------------------------------------------------
//  High-level loader the console calls on mount.
//  Mock mode → seed roster. Live mode → GET /patients (+ episodes) and adapt.
// ----------------------------------------------------------------------------

export async function getRoster(): Promise<Patient[]> {
  if (USE_MOCK) return seedPatients()

  const { data: patients } = await getPatients()
  const episodes = await Promise.all(
    patients.map((p) =>
      getPatientEpisode(p.id)
        .then((r) => r.data)
        .catch(() => undefined)
    )
  )
  const calls = await Promise.all(
    episodes.map((ep) =>
      ep
        ? getCallsForEpisode(ep.id)
            .then((r) => r.data)
            .catch(() => [] as ApiCall[])
        : Promise.resolve([] as ApiCall[])
    )
  )
  return patients.map((p, i) => toPatientVM(p, episodes[i], calls[i]))
}
