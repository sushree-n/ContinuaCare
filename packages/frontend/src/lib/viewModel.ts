import type React from 'react'
import type { Patient, StatusKind } from '../types'

// "Today" in the prototype's frame of reference.
const TODAY = new Date(2026, 5, 27) // Jun 27, 2026
const MO3 = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAY_MS = 86_400_000

type Seg = 'done' | 'pending' | 'flag' | 'todo'

export function hexA(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.substr(0, 2), 16)
  const g = parseInt(h.substr(2, 2), 16)
  const b = parseInt(h.substr(4, 2), 16)
  return `rgba(${r},${g},${b},${a})`
}

export function segState(p: Patient): [Seg, Seg, Seg] {
  const s1: Seg = p.flag ? 'flag' : p.contactDone ? 'done' : p.statusKind === 'calling' ? 'pending' : 'todo'
  const s2: Seg = p.visit ? 'done' : p.contactDone && !p.flag ? 'pending' : 'todo'
  const s3: Seg = p.ready ? 'done' : p.codeConfirmed ? 'pending' : 'todo'
  return [s1, s2, s3]
}

export function badgeStyle(kind: StatusKind): React.CSSProperties {
  const map: Record<string, string> = {
    ready: '#0E9A49',
    await: '#E0A211',
    window: '#032640',
    flag: '#E5331F',
    queued: '#7A756D',
    new: '#032640',
    calling: '#032640',
  }
  const c = map[kind] || map.queued
  return {
    display: 'inline-block',
    padding: '4px 12px',
    borderRadius: '100px',
    fontSize: '12px',
    fontWeight: 700,
    whiteSpace: 'nowrap',
    background: hexA(c, 0.12),
    border: '1px solid ' + hexA(c, 0.55),
    color: c,
  }
}

export function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
}

export function mrn(p: Patient): string {
  let h = 0
  for (let i = 0; i < p.id.length; i++) h = (h * 31 + p.id.charCodeAt(i)) >>> 0
  return '' + (10000 + (h % 89999))
}

export interface StatusInfo {
  text: string
  kind: StatusKind
}

export function statusInfo(p: Patient): StatusInfo {
  if (!p.hasEpisode) return { text: 'Pending discharge', kind: 'new' }
  if (p.statusKind === 'calling') return { text: 'Outreach in progress', kind: 'calling' }
  if (p.flag) return { text: 'Action required', kind: 'flag' }
  if (p.ready) return { text: 'Ready for billing', kind: 'ready' }
  if (!p.contactDone) return { text: 'Outreach in progress', kind: 'calling' }
  if (p.code && !p.codeConfirmed) return { text: 'Confirm code', kind: 'await' }
  return { text: 'Appointment scheduled', kind: 'window' }
}

function stepDot(state: Seg): React.CSSProperties {
  const map: Record<Seg, React.CSSProperties> = {
    done: { background: '#032640', color: '#fff' },
    pending: { background: '#FBF3E8', color: '#9A6B22', border: '1px solid #9A6B2240' },
    flag: { background: '#FBEFEF', color: '#B23B3B', border: '1px solid #B23B3B40' },
    todo: { background: '#F4F3F0', color: '#B6B1A8', border: '1px solid rgba(26,26,30,0.1)' },
  }
  return {
    width: '30px',
    height: '30px',
    borderRadius: '7px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '14px',
    fontWeight: 700,
    flexShrink: 0,
    ...map[state],
  }
}

const stepIcon = (st: Seg) => (st === 'done' ? '✓' : st === 'flag' ? '!' : st === 'pending' ? '•' : '○')

export interface Med {
  name: string
  dose: string
  freq: string
}

function dischargeDetail(p: Patient): { notes: string; meds: Med[] } {
  const dx = (p.dx || '').toLowerCase()
  let key = 'default'
  if (dx.includes('pneumonia')) key = 'pneumonia'
  else if (dx.includes('chf') || dx.includes('heart failure')) key = 'chf'
  else if (dx.includes('nstemi') || dx.includes('cardiac') || dx.includes('mi ')) key = 'cardiac'
  else if (dx.includes('copd')) key = 'copd'
  else if (dx.includes('diverticulitis')) key = 'gi'
  const map: Record<string, { notes: string; meds: Med[] }> = {
    pneumonia: {
      notes:
        'Completed IV antibiotics and transitioned to oral therapy. Afebrile for >24h prior to discharge, oxygen saturation stable on room air. Repeat chest X-ray advised in 4–6 weeks.',
      meds: [
        { name: 'Amoxicillin–clavulanate', dose: '875 mg', freq: 'Twice daily · 5 days' },
        { name: 'Azithromycin', dose: '250 mg', freq: 'Once daily · 3 days' },
        { name: 'Guaifenesin', dose: '600 mg', freq: 'As needed for cough' },
      ],
    },
    chf: {
      notes:
        'Diuresed to dry weight during admission. Counseled on daily weights and a 2 g sodium diet. Instructed to call if weight rises >3 lb in 2 days or breathing worsens.',
      meds: [
        { name: 'Furosemide', dose: '40 mg', freq: 'Once daily (AM)' },
        { name: 'Lisinopril', dose: '10 mg', freq: 'Once daily' },
        { name: 'Metoprolol succinate', dose: '25 mg', freq: 'Once daily' },
        { name: 'Spironolactone', dose: '25 mg', freq: 'Once daily' },
      ],
    },
    cardiac: {
      notes:
        'Managed medically without intervention. Dual antiplatelet therapy initiated. Cardiology follow-up arranged within one week; report any chest pain or bleeding immediately.',
      meds: [
        { name: 'Aspirin', dose: '81 mg', freq: 'Once daily' },
        { name: 'Ticagrelor', dose: '90 mg', freq: 'Twice daily' },
        { name: 'Atorvastatin', dose: '80 mg', freq: 'Once daily (PM)' },
        { name: 'Metoprolol tartrate', dose: '25 mg', freq: 'Twice daily' },
      ],
    },
    copd: {
      notes:
        'Treated for acute exacerbation with steroids and nebulizers. Inhaler technique reviewed at bedside. Pulmonary rehabilitation referral placed; complete the steroid taper as directed.',
      meds: [
        { name: 'Prednisone', dose: '40 mg', freq: 'Once daily · 5-day taper' },
        { name: 'Albuterol–ipratropium', dose: '1 inhalation', freq: 'Four times daily' },
        { name: 'Azithromycin', dose: '250 mg', freq: 'Once daily · 3 days' },
      ],
    },
    gi: {
      notes:
        'Diverticulitis resolved on antibiotics with no abscess on imaging. Advance to a high-fiber diet as tolerated. Outpatient colonoscopy recommended in 6 weeks.',
      meds: [
        { name: 'Ciprofloxacin', dose: '500 mg', freq: 'Twice daily · 7 days' },
        { name: 'Metronidazole', dose: '500 mg', freq: 'Three times daily · 7 days' },
        { name: 'Acetaminophen', dose: '650 mg', freq: 'As needed for pain' },
      ],
    },
    default: {
      notes:
        'Discharge summary on file. Continue home medications as prescribed and attend the scheduled follow-up visit.',
      meds: [],
    },
  }
  return map[key]
}

export function callSummary(p: Patient): string | null {
  if (!p.transcript || p.transcript.length === 0) return null
  const fn = p.name.split(' ')[0]
  if (p.flag) {
    const escalated = /handoff/i.test(p.flag) || p.status === 'Handoff complete'
    return (
      'ContinuaCare reached ' +
      fn +
      ' and ran the post-discharge check. ' +
      fn +
      ' reported concerning symptoms, so ContinuaCare escalated for urgent action and ' +
      (escalated ? 'completed a live handoff to the care team' : 'flagged the episode for an urgent callback') +
      '. No visit was booked on this call.'
    )
  }
  let s = 'ContinuaCare reached ' + fn + ', completed the symptom check and medication review with no acute concerns.'
  if (p.visit) s += ' A follow-up visit was booked for ' + p.visit.slot + (p.visit.provider ? ' with ' + p.visit.provider : '') + '.'
  if (p.code)
    s +=
      ' ContinuaCare recommends ' +
      p.code +
      (p.complexity ? ' (' + p.complexity.toLowerCase() + ')' : '') +
      (p.codeConfirmed ? ', confirmed by the provider' : ' for provider confirmation') +
      '.'
  return s
}

// ---------------------------------------------------------------------------
//  Table row view model
// ---------------------------------------------------------------------------

export interface RowVM {
  id: string
  pid: string
  name: string
  age: number
  sex: string
  daysSince: string
  dischargeDate: string
  facility: string
  dx: string
  statusText: string
  badgeStyle: React.CSSProperties
  rowStyle: React.CSSProperties
}

const ROW_GRID =
  'minmax(0,0.9fr) minmax(0,1.4fr) minmax(0,0.5fr) minmax(0,0.5fr) minmax(0,0.6fr) minmax(0,1fr) minmax(0,1.3fr) minmax(0,1.5fr) minmax(0,1.2fr)'

export function buildRow(p: Patient, selectedId: string | null): RowVM {
  const dDate = new Date(TODAY.getTime() - p.day * DAY_MS)
  const dischargeDate = MO3[dDate.getMonth()] + ' ' + dDate.getDate() + ', ' + dDate.getFullYear()
  const daysSince = p.day === 0 ? 'Today' : p.day === 1 ? '1 day' : p.day + ' days'
  const info = statusInfo(p)
  return {
    id: p.id,
    pid: mrn(p),
    name: p.name,
    age: p.age,
    sex: p.sex,
    daysSince,
    dischargeDate,
    facility: p.facility,
    dx: p.dx,
    statusText: info.text,
    badgeStyle: badgeStyle(info.kind),
    rowStyle: {
      display: 'grid',
      gridTemplateColumns: ROW_GRID,
      gap: '12px',
      alignItems: 'start',
      padding: '15px 0',
      cursor: 'pointer',
      borderBottom: '1px solid rgba(26,26,30,0.08)',
      background: p.id === selectedId ? '#EAF0F5' : 'transparent',
      transition: 'background .15s',
    },
  }
}

// ---------------------------------------------------------------------------
//  Detail-drawer view model
// ---------------------------------------------------------------------------

export interface CodeOption {
  code: string
  complexity: string
  amount: string
  isRec: boolean
  radioMark: string
  radioStyle: React.CSSProperties
  rowStyle: React.CSSProperties
  disabled: boolean
}

export interface SelVM {
  id: string
  name: string
  statusText: string
  badgePillStyle: React.CSSProperties
  progressFill: React.CSSProperties
  st1Dot: React.CSSProperties
  st1Icon: string
  st1Sub: string
  st1Date: string
  st2Dot: React.CSSProperties
  st2Icon: string
  st2Sub: string
  st2Date: string
  st3Dot: React.CSSProperties
  st3Icon: string
  st3Sub: string
  st3Date: string
  flag: boolean
  flagReason: string | null
  dob: string
  ageText: string
  sexFull: string
  pid: string
  facility: string
  dischargedDate: string
  dischargedAgo: string
  dx: string
  dischargeNotes: string
  meds: Med[]
  hasMeds: boolean
  contactStatus: string
  contactBadgeStyle: React.CSSProperties
  callDate: string
  hasTranscript: boolean
  noTranscript: boolean
  summary: string | null
  transcriptText: string
  hasVisit: boolean
  visitSlot: string
  visitProvider: string
  hasCode: boolean
  recCode: string | null
  codeOptions: CodeOption[]
  codeRationale: string | null
  codePending: boolean
  codeConfirmed: boolean
  confirmCodeBtn: string
  confirmedText: string
}

const CODE_TBL: Record<string, { cx: string; amt: string }> = {
  '99495': { cx: 'Moderate complexity', amt: '$201.20' },
  '99496': { cx: 'High complexity', amt: '$272.68' },
}

export function buildSel(p: Patient | null): SelVM | null {
  if (!p) return null
  const segs = segState(p)
  const subs1 = p.flag
    ? 'Action required'
    : p.contactDone
    ? 'Done · Day ' + p.contactDay
    : p.statusKind === 'calling'
    ? 'On the call…'
    : 'Queued by ContinuaCare'
  const subs2 = p.visit ? p.visit.slot : p.flag ? 'Pending callback' : 'Awaiting booking'
  const subs3 = p.ready ? '30 days clear' : p.codeConfirmed ? 'In 30-day window' : p.code ? 'Awaiting confirm' : '—'

  const fmtD = (dt: Date) => MO3[dt.getMonth()] + ' ' + dt.getDate()
  const fmtFull = (dt: Date) => MO3[dt.getMonth()] + ' ' + dt.getDate() + ', ' + dt.getFullYear()
  const dischargeDate = new Date(TODAY.getTime() - p.day * DAY_MS)
  const st1Date = p.contactDone ? fmtD(new Date(dischargeDate.getTime() + (p.contactDay || 0) * DAY_MS)) : '—'
  const st2Date = p.visit ? p.visit.slot.split('·')[0].trim() : '—'
  const billingDate = fmtD(new Date(dischargeDate.getTime() + 30 * DAY_MS))
  const st3Date = p.ready ? billingDate : p.codeConfirmed ? 'Est. ' + billingDate : '—'
  const filledSeg = (segs[1] === 'done' ? 1 : 0) + (segs[2] === 'done' ? 1 : 0)
  const parsedMeds: Med[] = (p.medications || []).map((m) => {
    const parts = m.split(' ')
    const name = parts[0] || m
    const dose = parts[1] || ''
    const freq = parts.slice(2).join(' ')
    return { name, dose, freq }
  })
  const ddNotes = p.discharge_notes || (p.hasEpisode ? 'Discharge summary on file.' : '')
  const sexFull = p.sex === 'F' ? 'Female' : 'Male'

  let hh = 0
  for (let i = 0; i < p.id.length; i++) hh = (hh * 17 + p.id.charCodeAt(i)) >>> 0
  const dob = MO3[hh % 12] + ' ' + (1 + ((hh >> 4) % 28)) + ', ' + (2026 - p.age)
  const pid = mrn(p)

  const dischargedDate = fmtFull(dischargeDate)
  const dischargedAgo = p.day === 0 ? 'Today' : p.day === 1 ? '1 day ago' : p.day + ' days ago'
  const contactDate = new Date(dischargeDate.getTime() + (p.contactDay || 0) * DAY_MS)
  const callDate = p.contactDone ? fmtFull(contactDate) : '—'

  let contactStatus = 'Pending'
  if (p.statusKind === 'calling') contactStatus = 'Ongoing'
  else if (p.contactFailed) contactStatus = 'Failed'
  else if (p.contactDone) contactStatus = 'Reached'
  const cMap: Record<string, string> = { Reached: '#0E9A49', Ongoing: '#E0A211', Pending: '#032640', Failed: '#E5331F' }
  const csC = cMap[contactStatus]
  const contactBadgeStyle: React.CSSProperties = {
    display: 'inline-block',
    marginTop: '4px',
    padding: '4px 13px',
    borderRadius: '100px',
    fontSize: '13px',
    fontWeight: 700,
    background: hexA(csC, 0.12),
    color: csC,
    border: '1px solid ' + hexA(csC, 0.55),
  }

  const recCode = p.recCode || p.code
  const codeOptions: CodeOption[] = p.code
    ? ['99495', '99496'].map((c) => {
        const sel2 = c === p.code
        const isRec = c === recCode
        return {
          code: c,
          complexity: CODE_TBL[c].cx,
          amount: CODE_TBL[c].amt,
          isRec,
          radioMark: sel2 ? '●' : '',
          radioStyle: {
            width: '18px',
            height: '18px',
            borderRadius: '50%',
            border: '2px solid ' + (sel2 ? '#032640' : '#C4C0B8'),
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '9px',
            color: '#032640',
            flexShrink: 0,
          },
          disabled: p.codeConfirmed,
          rowStyle: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '13px 16px',
            borderRadius: '10px',
            cursor: p.codeConfirmed ? 'default' : 'pointer',
            border: '1px solid ' + (sel2 ? '#032640' : 'rgba(26,26,30,0.14)'),
            background: sel2 ? '#EAF0F5' : '#fff',
            opacity: p.codeConfirmed && !sel2 ? 0.45 : 1,
            transition: 'border-color .15s, background .15s',
          },
        }
      })
    : []

  const transcriptText = (p.transcript || [])
    .map((t) => (t.who === 'agent' ? 'ContinuaCare' : p.name.split(' ')[0]) + ': ' + t.text)
    .join('\n')
  const info = statusInfo(p)

  return {
    id: p.id,
    name: p.name,
    statusText: info.text,
    badgePillStyle: { ...badgeStyle(info.kind), borderRadius: '100px', padding: '5px 13px' },
    progressFill: {
      width: (filledSeg / 2) * 100 + '%',
      height: '100%',
      background: '#032640',
      borderRadius: '2px',
      transition: 'width .3s',
    },
    st1Dot: stepDot(segs[0]),
    st1Icon: stepIcon(segs[0]),
    st1Sub: subs1,
    st1Date,
    st2Dot: stepDot(segs[1]),
    st2Icon: stepIcon(segs[1]),
    st2Sub: subs2,
    st2Date,
    st3Dot: stepDot(segs[2]),
    st3Icon: stepIcon(segs[2]),
    st3Sub: subs3,
    st3Date,
    flag: !!p.flag,
    flagReason: p.flag,
    dob,
    ageText: p.age + ' years',
    sexFull,
    pid,
    facility: p.facility,
    dischargedDate,
    dischargedAgo,
    dx: p.dx,
    dischargeNotes: ddNotes,
    meds: parsedMeds,
    hasMeds: parsedMeds.length > 0,
    contactStatus,
    contactBadgeStyle,
    callDate,
    hasTranscript: (p.transcript || []).length > 0,
    noTranscript: (p.transcript || []).length === 0,
    summary: p.callSummary ?? callSummary(p),
    transcriptText,
    hasVisit: !!p.visit,
    visitSlot: p.visit ? p.visit.slot : '',
    visitProvider: p.visit ? p.visit.provider : '',
    hasCode: !!p.code,
    recCode,
    codeOptions,
    codeRationale: p.codeRationale,
    codePending: !p.codeConfirmed,
    codeConfirmed: p.codeConfirmed,
    confirmCodeBtn: 'Confirm ' + (p.code || '') + ' as provider →',
    confirmedText: p.code ? p.code + ' confirmed · ' + (CODE_TBL[p.code] ? CODE_TBL[p.code].amt : '') : '',
  }
}
