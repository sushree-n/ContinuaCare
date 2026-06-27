import { create } from 'zustand'
import type { FilterKey, Patient } from '../types'
import { dischargeJobs, seedPatients } from '../mockData'
import { createEpisode, getOpenEscalations, getRoster, USE_MOCK } from '../api'

interface ContinuaCareState {
  // data
  patients: Patient[]
  jobIndex: number
  hydrated: boolean
  openEscalationIds: Set<string>

  // ui state
  selectedId: string | null
  drawerOpen: boolean
  panelWidth: number
  filter: FilterKey | null
  transcriptOpen: boolean
  staffAvailable: boolean
  dischargeModal: { patientId: string; patientName: string } | null

  // data actions
  hydrate: () => Promise<void>
  startEscalationPolling: () => () => void
  triggerDischarge: () => void
  initiateDischarge: (patientId: string, patientName: string) => void
  submitDischarge: (patientId: string, dischargeDate: string, notes: string) => Promise<void>
  confirmCode: (id: string) => void
  chooseCode: (id: string, code: string) => void
  markReviewed: (id: string) => void

  // ui actions
  select: (id: string) => void
  closeDrawer: () => void
  closeDischargeModal: () => void
  setFilter: (k: FilterKey) => void
  toggleTranscript: () => void
  toggleStaff: () => void
  setPanelWidth: (w: number) => void
}

export const useStore = create<ContinuaCareState>((set, get) => ({
  patients: seedPatients(),
  jobIndex: 0,
  hydrated: false,
  openEscalationIds: new Set(),

  selectedId: null,
  drawerOpen: false,
  panelWidth: 560,
  filter: null,
  transcriptOpen: false,
  staffAvailable: true,
  dischargeModal: null,

  // On mount: mock mode keeps the seed roster; live mode pulls from the API.
  hydrate: async () => {
    if (get().hydrated) return
    try {
      const roster = await getRoster()
      set({ patients: roster, hydrated: true })
    } catch {
      set({ hydrated: true })
    }
  },

  // Poll /escalations/open every 3s and flip matching patient statusKind to 'flag'.
  startEscalationPolling: () => {
    if (USE_MOCK) return () => {}
    const poll = async () => {
      try {
        const { data } = await getOpenEscalations()
        const ids = new Set(data.map((e) => e.episode_id))
        set((s) => ({
          openEscalationIds: ids,
          patients: s.patients.map((p) => {
            const escalated = data.some((e) => e.episode_id === p.id || s.patients.find(pt => pt.id === p.id))
            // match by episode — we need to track episode_id on patient for this
            // for now flag any patient whose id appears in escalation episode_ids
            const hasFlag = data.some((e) => {
              // episode_id won't match patient.id directly; we store episode_id in patient status
              return false // placeholder — see note below
            })
            return p
          }),
        }))
      } catch { /* silently ignore poll errors */ }
    }
    poll()
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  },

  initiateDischarge: (patientId, patientName) =>
    set({ dischargeModal: { patientId, patientName } }),

  closeDischargeModal: () => set({ dischargeModal: null }),

  submitDischarge: async (patientId, dischargeDate, notes) => {
    const { data: episode } = await createEpisode({
      patient_id: patientId,
      discharge_date: dischargeDate,
      discharge_notes: notes,
    })
    // Update the patient's status in the roster immediately
    set((s) => ({
      dischargeModal: null,
      patients: s.patients.map((p) =>
        p.id === patientId
          ? { ...p, status: 'discharge_detected', statusKind: 'new', dischargeText: 'Just now · Day 0', dayLine: 'Just now · Day 0', day: 0 }
          : p
      ),
    }))
    return void episode
  },

  triggerDischarge: () =>
    set((s) => {
      const jobs = dischargeJobs()
      const job = jobs[s.jobIndex % 3]
      // jobIndex suffix keeps the id unique even on rapid (same-millisecond) clicks.
      const id = 'p_new_' + Date.now() + '_' + s.jobIndex
      let extra: Partial<Patient>
      if (job.scenario === 'flag') {
        extra = {
          contactDone: true,
          contactDay: 0,
          status: 'Flagged · callback',
          statusKind: 'flag',
          visit: { slot: 'Within 7 days · to confirm', provider: 'First available' },
          code: '99496',
          complexity: 'High complexity',
          codeAmount: '$272.68',
          codeRationale:
            'Concerning symptoms on the contact call warrant an expedited face-to-face visit within 7 days; high decision-making supports 99496 pending the visit.',
          codeConfirmed: false,
          flag:
            'Concerning symptoms on the contact call (recurrent fever, shortness of breath). Flagged for clinical review, the follow-up visit is still scheduled within 7 days, but the care team should review these symptoms and decide if earlier action is needed.',
        }
      } else {
        extra = {
          contactDone: true,
          contactDay: 0,
          status: 'Awaiting code confirm',
          statusKind: 'await',
          visit: job.visit ?? null,
          code: job.code ?? null,
          complexity: job.complexity ?? null,
          codeAmount: job.codeAmount ?? null,
          codeRationale: job.codeRationale ?? null,
          codeConfirmed: false,
        }
      }
      const np: Patient = {
        id,
        name: job.name,
        age: job.age,
        sex: job.sex,
        phone: job.phone,
        facility: job.facility,
        dischargeText: 'Just now · Day 0',
        dayLine: 'Just now · Day 0',
        day: 0,
        dx: job.dx,
        visit: null,
        code: null,
        complexity: null,
        codeAmount: null,
        codeRationale: null,
        codeConfirmed: false,
        flag: null,
        ready: false,
        transcript: job.lines,
        status: '',
        statusKind: 'new',
        contactDone: false,
        contactDay: null,
        ...extra,
      }
      return { patients: [np, ...s.patients], jobIndex: s.jobIndex + 1 }
    }),

  confirmCode: (id) =>
    set((s) => ({
      patients: s.patients.map((p) =>
        p.id === id
          ? {
              ...p,
              codeConfirmed: true,
              status: p.day >= 30 ? 'Ready for billing' : 'In 30-day window',
              statusKind: p.day >= 30 ? 'ready' : 'window',
              ready: p.day >= 30,
            }
          : p
      ),
    })),

  chooseCode: (id, code) =>
    set((s) => ({
      patients: s.patients.map((p) => {
        if (p.id !== id || p.codeConfirmed) return p
        const rec = p.recCode || p.code || undefined
        const recRat = p.recRationale || p.codeRationale || undefined
        const cx = code === '99496' ? 'High complexity' : 'Moderate complexity'
        const amt = code === '99496' ? '$272.68' : '$201.20'
        return {
          ...p,
          recCode: rec,
          recRationale: recRat,
          code,
          complexity: cx,
          codeAmount: amt,
          codeRationale:
            code === rec
              ? recRat ?? null
              : 'Provider override, ' +
                code +
                ' (' +
                cx.toLowerCase() +
                ') selected in place of the recommended ' +
                rec +
                '. Documentation should support the higher level of service.',
        }
      }),
    })),

  markReviewed: (id) =>
    set((s) => ({
      patients: s.patients.map((p) =>
        p.id === id
          ? {
              ...p,
              flag: null,
              status: p.code && !p.codeConfirmed ? 'Awaiting code confirm' : 'Appointment scheduled',
              statusKind: p.code && !p.codeConfirmed ? 'await' : 'window',
            }
          : p
      ),
    })),

  select: (id) => set({ selectedId: id, drawerOpen: true, transcriptOpen: false }),
  closeDrawer: () => set({ drawerOpen: false, selectedId: null }),
  setFilter: (k) => set((s) => ({ filter: s.filter === k ? null : k })),
  toggleTranscript: () => set((s) => ({ transcriptOpen: !s.transcriptOpen })),
  toggleStaff: () => set((s) => ({ staffAvailable: !s.staffAvailable })),
  setPanelWidth: (w) => set({ panelWidth: w }),
}))

// KPI filter predicate (ported from the prototype's matchFilter).
export function matchFilter(p: Patient, k: FilterKey | null): boolean {
  if (!k) return true
  if (k === 'active') return !p.ready
  if (k === 'flag') return !!p.flag
  if (k === 'confirm') return !!p.code && !p.codeConfirmed && !p.flag && !p.ready
  if (k === 'ready') return !!p.ready
  return true
}
