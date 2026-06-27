// ============================================================================
//  UI MODEL, drives the ContinuaCare console (mirrors the design prototype's data)
// ============================================================================

export type StatusKind =
  | 'ready'
  | 'await'
  | 'window'
  | 'flag'
  | 'queued'
  | 'new'
  | 'calling'

/** KPI cards double as table filters. */
export type FilterKey = 'active' | 'flag' | 'confirm' | 'ready'

export interface Visit {
  slot: string
  provider: string
}

export interface TranscriptLine {
  who: 'agent' | 'patient'
  text: string
  danger?: boolean
  chip?: string
}

export interface Patient {
  id: string
  name: string
  age: number
  sex: 'F' | 'M'
  phone: string
  facility: string
  dischargeText: string
  dayLine: string
  day: number
  dx: string
  status: string
  statusKind: StatusKind
  contactDone: boolean
  contactDay: number | null
  contactFailed?: boolean
  visit: Visit | null
  code: string | null
  complexity: string | null
  codeAmount: string | null
  codeRationale: string | null
  codeConfirmed: boolean
  recCode?: string
  recRationale?: string
  flag: string | null
  ready: boolean
  transcript: TranscriptLine[]
}

/** A "discharge" scenario the Simulate Discharge button cycles through. */
export interface DischargeJob {
  name: string
  age: number
  sex: 'F' | 'M'
  phone: string
  facility: string
  dx: string
  scenario: 'clean' | 'flag' | 'high'
  code?: string
  complexity?: string
  codeAmount?: string
  codeRationale?: string
  visit?: Visit
  lines: TranscriptLine[]
}

// ============================================================================
//  BACKEND DTOs, ContinuaCare API (master spec §3/§4)
//  Kept here so api.ts is ready to connect to the real FastAPI backend.
// ============================================================================

export type EpisodeState =
  | 'discharge_detected'
  | 'awaiting_call'
  | 'call_in_progress'
  | 'call_complete'
  | 'escalated'
  | 'visit_scheduled'
  | 'ready_to_bill'
  | 'voided'

export type ComplexityLevel = 'high' | 'moderate'

export type CallStatus =
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'no_answer'
  | 'failed'

export type EscalationStatus = 'open' | 'resolved'

export interface ApiPatient {
  id: string
  name: string
  age: number
  phone: string
  diagnosis: string
  medications: string[]
  patient_history: string
  created_at: string
}

export interface ApiEpisode {
  id: string
  patient_id: string
  state: EpisodeState
  discharge_date: string
  discharge_notes?: string
  structured_extract?: unknown
  complexity?: ComplexityLevel
  triage_reason?: string
  visit_window_days?: number
  contact_deadline?: string
  visit_deadline?: string
  billing_date?: string
  face_to_face_date?: string
  med_rec_completed?: boolean
  med_rec_date?: string
  cpt_code?: string
  billing_doc?: string
  ready_to_bill?: boolean
}

export interface ApiCall {
  id: string
  episode_id: string
  patient_id: string
  attempt_number: number
  status: CallStatus
  transcript?: string
  summary?: string
  flags?: string[]
  structured_data?: unknown
}

export interface ApiEscalation {
  id: string
  episode_id: string
  call_id?: string | null
  reason: string
  severity: 'urgent' | 'monitor'
  status: EscalationStatus
  created_at: string
  acknowledged_at?: string | null
}
