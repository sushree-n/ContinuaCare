import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { css, H } from '../lib/ui'
import { matchFilter, useStore } from '../store/useStore'
import { buildRow, buildSel } from '../lib/viewModel'
import type { FilterKey } from '../types'

const AMOUNTS: Record<string, number> = { '99495': 201.2, '99496': 272.68 }

const SECTION_HEADER = css(
  'font-size:19px;font-weight:700;letter-spacing:0.02em;text-transform:uppercase;color:#032640;padding:10px 0 20px;display:flex;align-items:center;gap:13px'
)
const LABEL = css('font-size:11.5px;letter-spacing:0.03em;text-transform:uppercase;color:#A39E96;margin-bottom:3px')
const VALUE = css('font-weight:600;font-size:15px')

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={SECTION_HEADER}>
      {children}
      <span style={css('flex:1;height:2px;background:rgba(26,26,30,0.2)')} />
    </div>
  )
}

export default function Demo() {
  const {
    patients,
    selectedId,
    drawerOpen,
    panelWidth,
    filter,
    transcriptOpen,
    dischargeModal,
    hydrate,
    startEscalationPolling,
    triggerDischarge,
    initiateDischarge,
    submitDischarge,
    closeDischargeModal,
    confirmCode,
    chooseCode,
    markReviewed,
    select,
    closeDrawer,
    setFilter,
    toggleTranscript,
    setPanelWidth,
  } = useStore()

  const [dischargeDate, setDischargeDate] = useState(new Date().toISOString().slice(0, 16))
  const [dischargeNotes, setDischargeNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const stopPollingRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    hydrate()
    stopPollingRef.current = startEscalationPolling()
    return () => stopPollingRef.current?.()
  }, [hydrate, startEscalationPolling])

  const handleDischargeSubmit = async () => {
    if (!dischargeModal || !dischargeNotes.trim()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await submitDischarge(dischargeModal.patientId, new Date(dischargeDate).toISOString(), dischargeNotes)
      setDischargeNotes('')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      setSubmitError(msg || 'Failed to create episode — check the backend is running.')
    } finally {
      setSubmitting(false)
    }
  }

  // ----- KPIs -----
  const active = patients.filter((p) => !p.ready).length
  const flagged = patients.filter((p) => p.flag).length
  const confirm = patients.filter((p) => p.code && !p.codeConfirmed && !p.flag && !p.ready).length
  const readyList = patients.filter((p) => p.ready)
  const readyAmount = '$' + readyList.reduce((s, p) => s + (AMOUNTS[p.code || ''] || 0), 0).toFixed(2)

  // ----- roster rows -----
  const rows = patients
    .slice()
    .filter((p) => matchFilter(p, filter))
    .sort((a, b) => (b.flag ? 1 : 0) - (a.flag ? 1 : 0))
    .map((p) => buildRow(p, selectedId))

  // ----- detail -----
  const selPatient = patients.find((p) => p.id === selectedId) || null
  const sel = buildSel(selPatient)
  const open = drawerOpen && !!sel

  const maxPw = Math.max(380, window.innerWidth - 380)
  const pw = Math.min(panelWidth, maxPw)

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = panelWidth
    const onMove = (ev: MouseEvent) => {
      const dx = startX - ev.clientX
      const max = Math.max(380, window.innerWidth - 380)
      setPanelWidth(Math.max(380, Math.min(max, startW + dx)))
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      document.body.style.userSelect = ''
    }
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const kpiCard = (kind: FilterKey, accent: string): React.CSSProperties => ({
    borderRadius: '10px',
    padding: '16px 20px',
    cursor: 'pointer',
    background: filter === kind ? '#fff' : '#F1F1F3',
    border: '1px solid ' + (filter === kind ? accent : 'transparent'),
    boxShadow: filter === kind ? '0 1px 6px rgba(26,26,30,0.07)' : 'none',
    transition: 'background .15s, border-color .15s',
  })

  return (
    <div style={css('height:100vh;width:100%;display:flex;flex-direction:column;overflow:hidden')}>
      {/* ===== TOP BAR ===== */}
      <div style={css('flex-shrink:0;z-index:40;background:rgba(255,255,255,0.92);backdrop-filter:blur(10px);border-bottom:1px solid rgba(26,26,30,0.1)')}>
        <div style={css('max-width:1320px;margin:0 auto;padding:13px 26px;display:flex;align-items:center;justify-content:space-between')}>
          <div style={css('display:flex;align-items:center;gap:16px')}>
          <H as={Link} to="/" style={css('display:flex;align-items:center;gap:10px')} hoverStyle={{ opacity: 0.75 }}>
            <div style={css('width:30px;height:30px;border-radius:9px;background:#032640;display:flex;align-items:center;justify-content:center;gap:2px')}>
              <span style={css('width:2.5px;height:8px;border-radius:2px;background:#7FD3A5')} />
              <span style={css('width:2.5px;height:13px;border-radius:2px;background:#fff')} />
              <span style={css('width:2.5px;height:9px;border-radius:2px;background:#CFE3C8')} />
            </div>
            <span className="disp" style={css('font-size:19px;font-weight:700')}>ContinuaCare</span>
            <span style={css('font-size:13px;color:#9A968F;font-weight:500;margin-left:2px')}>Care console</span>
          </H>
        </div>
        <div style={css('display:flex;align-items:center;gap:14px')}>
          <H
            as="button"
            onClick={triggerDischarge}
            style={css('display:flex;align-items:center;gap:9px;background:#032640;color:#fff;font-weight:600;font-size:14.5px;padding:11px 16px 11px 18px;border:none;border-radius:8px;cursor:pointer')}
            hoverStyle={{ background: '#33323a' }}
          >
            <span style={css('font-size:15px')}>＋</span> Simulate Discharge
          </H>
        </div>
        </div>
      </div>

      {/* ===== SPLIT WORKSPACE ===== */}
      <div style={css('flex:1;min-height:0;display:flex;align-items:stretch;width:100%')}>
        {/* LEFT PANE */}
        <div className="cc-scroll" style={css('flex:1;min-width:0;overflow:hidden;display:flex;flex-direction:column')}>
          <div style={css('max-width:1320px;width:100%;margin:0 auto;padding:24px 26px 24px;display:flex;flex-direction:column;flex:1;min-height:0')}>
            {/* KPI ROW */}
            <div style={css('display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px;flex-shrink:0')}>
              <div onClick={() => setFilter('active')} style={kpiCard('active', '#032640')}>
                <div style={css('display:flex;align-items:center;gap:7px;font-size:12px;color:#6B6770;font-weight:600;margin-bottom:10px')}><span style={css('width:7px;height:7px;border-radius:50%;background:#032640')} />Total active cases</div>
                <div className="disp" style={css('font-size:32px;font-weight:700;color:#032640')}>{active}</div>
              </div>
              <div onClick={() => setFilter('flag')} style={kpiCard('flag', '#E5331F')}>
                <div style={css('display:flex;align-items:center;gap:7px;font-size:12px;color:#6B6770;font-weight:600;margin-bottom:10px')}><span style={css('width:7px;height:7px;border-radius:50%;background:#E5331F')} />Action required</div>
                <div className="disp" style={css('font-size:32px;font-weight:700;color:#E5331F')}>{flagged}</div>
              </div>
              <div onClick={() => setFilter('confirm')} style={kpiCard('confirm', '#E0A211')}>
                <div style={css('display:flex;align-items:center;gap:7px;font-size:12px;color:#6B6770;font-weight:600;margin-bottom:10px')}><span style={css('width:7px;height:7px;border-radius:50%;background:#E0A211')} />Confirm code</div>
                <div className="disp" style={css('font-size:32px;font-weight:700;color:#E0A211')}>{confirm}</div>
              </div>
              <div onClick={() => setFilter('ready')} style={kpiCard('ready', '#0E9A49')}>
                <div style={css('display:flex;align-items:center;justify-content:space-between')}>
                  <div>
                    <div style={css('display:flex;align-items:center;gap:7px;font-size:12px;color:#6B6770;font-weight:600;margin-bottom:10px')}><span style={css('width:7px;height:7px;border-radius:50%;background:#0E9A49')} />Ready to bill</div>
                    <div className="disp" style={css('font-size:32px;font-weight:700;color:#0E9A49')}>{readyList.length}</div>
                  </div>
                  <div style={css('text-align:right')}>
                    <div className="disp" style={css('font-size:18px;font-weight:700;color:#0E9A49')}>{readyAmount}</div>
                    <div style={css('font-size:11px;color:#9A968F')}>captured</div>
                  </div>
                </div>
              </div>
            </div>

            {/* ROSTER */}
            <div style={css('background:#fff;overflow:hidden;padding:0 24px;flex:1;min-height:0;display:flex;flex-direction:column')}>
              <div style={css('display:flex;align-items:center;justify-content:space-between;padding:4px 0 16px;flex-shrink:0')}>
                <div>
                  <div className="disp" style={css('font-size:21px;font-weight:700')}>Patient roster</div>
                  <div style={css('font-size:13px;color:#9A968F;margin-top:2px')}>TCM episodes in the 30-day window · click a patient to open the record</div>
                </div>
              </div>

              <div className="cc-scroll" style={{ overflowY: 'auto', overflowX: open ? 'auto' : 'hidden', flex: 1, minHeight: 0 }}>
                <div style={{ minWidth: open ? '880px' : '100%' }}>
                  {/* column head */}
                  <div style={css('display:grid;grid-template-columns:minmax(0,0.9fr) minmax(0,1.4fr) minmax(0,0.5fr) minmax(0,0.5fr) minmax(0,0.6fr) minmax(0,1fr) minmax(0,1.3fr) minmax(0,1.5fr) minmax(0,1.2fr);gap:12px;padding:9px 0;border-top:1px solid rgba(26,26,30,0.06);border-bottom:1px solid rgba(26,26,30,0.06);font-size:11.5px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#A39E96')}>
                    <div>Patient ID</div><div>PATIENT NAME</div><div>Age</div><div>Sex</div><div>Days</div><div>Discharged</div><div>Hospital</div><div>Reason for hospitalization</div><div>Status</div>
                  </div>
                  {/* rows */}
                  <div>
                    {rows.map((row) => (
                      <H key={row.id} onClick={() => select(row.id)} style={row.rowStyle} hoverStyle={{ background: 'rgba(26,26,30,0.025)' }}>
                        <div style={css('font-size:13.5px;color:#3A3A40;font-family:monospace')}>{row.pid}</div>
                        <div style={css('font-weight:700;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0')}>{row.name}</div>
                        <div style={css('font-size:13.5px;color:#3A3A40')}>{row.age}</div>
                        <div style={css('font-size:13.5px;color:#3A3A40')}>{row.sex}</div>
                        <div style={css('font-size:13.5px;font-weight:700')}>{row.daysSince}</div>
                        <div style={css('font-size:13.5px;color:#3A3A40')}>{row.dischargeDate}</div>
                        <div style={css('font-size:13.5px;color:#3A3A40;white-space:nowrap;overflow:hidden;text-overflow:ellipsis')}>{row.facility}</div>
                        <div style={css('font-size:13.5px;color:#3A3A40;line-height:1.35')}>{row.dx}</div>
                        <div><span style={row.badgeStyle}>{row.statusText}</span></div>
                      </H>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div style={css('text-align:center;font-size:12px;color:#A39E96;margin-top:14px;flex-shrink:0')}>Demo data · ContinuaCare hackathon prototype · not for clinical use</div>
          </div>
        </div>

        {/* ===== RESIZABLE DETAIL PANEL ===== */}
        {sel && (
          <>
            <div onMouseDown={startResize} style={css('flex-shrink:0;width:12px;cursor:col-resize;display:flex;align-items:center;justify-content:center;background:rgba(26,26,30,0.04);border-left:1px solid rgba(26,26,30,0.09);touch-action:none')}>
              <div style={css('width:4px;height:46px;border-radius:4px;background:rgba(26,26,30,0.2)')} />
            </div>
            <aside className="cc-scroll" style={{ flexShrink: 0, width: pw + 'px', overflowY: 'auto', overflowX: 'hidden', background: '#FFFFFF', borderLeft: '1px solid rgba(26,26,30,0.07)', animation: 'slidein .25s ease both' }}>
              {/* sticky header */}
              <div style={css('position:sticky;top:0;background:rgba(255,255,255,0.94);backdrop-filter:blur(10px);border-bottom:1px solid rgba(26,26,30,0.1);padding:18px 22px;z-index:3')}>
                <div style={css('display:flex;align-items:flex-start;justify-content:space-between;gap:12px')}>
                  <div style={css('display:flex;align-items:center;gap:13px;min-width:0')}>
                    <div style={{ minWidth: 0 }}>
                      <div style={css('display:flex;align-items:center;gap:10px;flex-wrap:wrap')}>
                        <div className="disp" style={css('font-size:21px;font-weight:700;line-height:1.05')}>{sel.name}</div>
                        <span style={sel.badgePillStyle}>{sel.statusText}</span>
                      </div>
                    </div>
                  </div>
                  <div style={css('display:flex;align-items:center;gap:8px')}>
                    {!selPatient?.hasEpisode && (
                      <H
                        as="button"
                        onClick={() => selPatient && initiateDischarge(selPatient.id, selPatient.name)}
                        style={css('display:flex;align-items:center;gap:7px;background:#032640;color:#fff;font-weight:600;font-size:13px;padding:8px 14px;border:none;border-radius:7px;cursor:pointer;white-space:nowrap')}
                        hoverStyle={{ background: '#0a3a5c' }}
                      >
                        ＋ Initiate Discharge
                      </H>
                    )}
                    <H as="button" onClick={closeDrawer} style={css('width:32px;height:32px;flex-shrink:0;border-radius:7px;border:1px solid rgba(26,26,30,0.12);background:#fff;color:#6B6770;font-size:14px;cursor:pointer')} hoverStyle={{ background: 'rgba(26,26,30,0.06)' }}>✕</H>
                  </div>
                </div>
              </div>

              {/* TCM pipeline */}
              <div style={css('padding:20px 22px 0')}>
                <div style={css('position:relative;display:flex;justify-content:space-between')}>
                  <div style={css('position:absolute;top:15px;left:16.7%;right:16.7%;height:3px;background:#EDE9E1;border-radius:2px;overflow:hidden')}>
                    <div style={sel.progressFill} />
                  </div>
                  {([
                    { dot: sel.st1Dot, icon: sel.st1Icon, label: 'Contact', sub: sel.st1Sub, date: sel.st1Date },
                    { dot: sel.st2Dot, icon: sel.st2Icon, label: 'Visit', sub: sel.st2Sub, date: sel.st2Date },
                    { dot: sel.st3Dot, icon: sel.st3Icon, label: 'Billing', sub: sel.st3Sub, date: sel.st3Date },
                  ]).map((st, i) => (
                    <div key={i} style={css('position:relative;display:flex;flex-direction:column;align-items:center;flex:1;text-align:center')}>
                      <div style={st.dot}>{st.icon}</div>
                      <div style={css('font-weight:700;font-size:13px;margin-top:10px')}>{st.label}</div>
                      <div style={css('font-size:12px;color:#9A968F;line-height:1.3;margin-top:1px')}>{st.sub}</div>
                      <div style={css('font-size:11.5px;color:#032640;font-weight:600;margin-top:3px')}>{st.date}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* body */}
              <div style={css('padding:22px')}>
                {sel.flag && (
                  <div style={css('background:rgba(229,51,31,0.1);border:1px solid rgba(229,51,31,0.55);border-radius:8px;padding:16px 20px;margin-bottom:22px;display:flex;align-items:center;justify-content:space-between;gap:24px;flex-wrap:wrap')}>
                    <div style={css('flex:1;min-width:320px')}>
                      <div style={css('display:flex;align-items:center;gap:8px;font-weight:700;color:#E5331F;font-size:15px;margin-bottom:6px')}>⚠ Urgent action required</div>
                      <div style={css('font-size:14px;line-height:1.45;color:#C42718')}>{sel.flagReason}</div>
                    </div>
                    <H as="button" onClick={() => markReviewed(sel.id)} style={css('background:#E5331F;color:#fff;border:none;font-weight:700;font-size:14px;padding:11px 18px;border-radius:8px;cursor:pointer;white-space:nowrap')} hoverStyle={{ background: '#C42718' }}>Mark reviewed</H>
                  </div>
                )}

                <div style={css('display:flex;flex-direction:column;gap:44px')}>
                  {/* PATIENT INFO */}
                  <div style={css('padding-bottom:4px')}>
                    <SectionHeader>Patient info</SectionHeader>
                    <div style={css('display:grid;grid-template-columns:1fr 1fr;gap:16px 22px')}>
                      <div><div style={LABEL}>Date of birth</div><div style={VALUE}>{sel.dob}</div></div>
                      <div><div style={LABEL}>Age</div><div style={VALUE}>{sel.ageText}</div></div>
                      <div><div style={LABEL}>Sex</div><div style={VALUE}>{sel.sexFull}</div></div>
                      <div><div style={LABEL}>Patient ID</div><div style={{ ...VALUE, fontFamily: 'monospace' }}>{sel.pid}</div></div>
                    </div>
                  </div>

                  {/* DISCHARGE INFO */}
                  <div style={css('padding-bottom:4px')}>
                    <SectionHeader>Discharge info</SectionHeader>
                    <div style={css('display:grid;grid-template-columns:1fr 1fr;gap:16px 22px')}>
                      <div><div style={LABEL}>Facility</div><div style={VALUE}>{sel.facility}</div></div>
                      <div>
                        <div style={LABEL}>Discharged</div>
                        <div style={VALUE}>{sel.dischargedDate}</div>
                        <div style={css('font-size:12.5px;color:#9A968F;margin-top:1px')}>{sel.dischargedAgo}</div>
                      </div>
                      <div style={{ gridColumn: 'span 2' }}><div style={LABEL}>Reason for hospitalization</div><div style={VALUE}>{sel.dx}</div></div>
                      <div style={{ gridColumn: 'span 2' }}><div style={LABEL}>Discharge notes</div><div style={css('font-size:13.5px;line-height:1.5;color:#3A3A40')}>{sel.dischargeNotes}</div></div>
                      {sel.hasMeds && (
                        <div style={{ gridColumn: 'span 2' }}>
                          <div style={{ ...LABEL, marginBottom: '9px' }}>Discharge medications</div>
                          <div style={css('border:1px solid rgba(26,26,30,0.12);border-radius:10px;overflow:hidden')}>
                            {sel.meds.map((m, i) => (
                              <div key={i} style={css('display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 14px;border-bottom:1px solid rgba(26,26,30,0.07)')}>
                                <div style={css('display:flex;align-items:center;gap:10px;min-width:0')}>
                                  <span style={css('width:6px;height:6px;border-radius:50%;background:#0E9A49;flex-shrink:0')} />
                                  <span style={css('font-weight:600;font-size:14px')}>{m.name}</span>
                                  <span style={css('font-size:13px;color:#6B6770')}>{m.dose}</span>
                                </div>
                                <span style={css('font-size:13.5px;line-height:1.5;color:#3A3A40;white-space:nowrap')}>{m.freq}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 2-DAY CONTACT */}
                  <div style={css('padding-bottom:4px')}>
                    <SectionHeader>2-day contact</SectionHeader>
                    <div style={css('display:grid;grid-template-columns:1fr 1fr;gap:16px 22px;margin-bottom:20px')}>
                      <div><div style={LABEL}>Contact status</div><span style={sel.contactBadgeStyle}>{sel.contactStatus}</span></div>
                      <div><div style={LABEL}>Call date</div><div style={VALUE}>{sel.callDate}</div></div>
                    </div>
                    {sel.hasTranscript && (
                      <>
                        <div style={{ ...LABEL, marginBottom: '8px' }}>Call summary</div>
                        <div style={css('background:#F6F6F8;border-radius:10px;padding:16px 18px;font-size:14px;line-height:1.55;color:#3A3A40')}>{sel.summary}</div>
                        <div style={css('display:flex;justify-content:flex-start;margin-top:10px')}>
                          <span onClick={toggleTranscript} style={css('font-size:13.5px;font-weight:600;color:#032640;text-decoration:underline;cursor:pointer')}>{transcriptOpen ? 'Hide full transcript' : 'View full transcript'}</span>
                        </div>
                        {transcriptOpen && (
                          <div className="cc-scroll" style={css('margin-top:10px;border:1px solid rgba(26,26,30,0.12);border-radius:10px;padding:18px;max-height:340px;overflow-y:auto;background:#fff;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.7;color:#3A3A40;white-space:pre-wrap')}>{sel.transcriptText}</div>
                        )}
                      </>
                    )}
                    {sel.noTranscript && (
                      <div style={css('background:#fff;border:1px dashed rgba(26,26,30,0.16);border-radius:8px;padding:30px 24px;text-align:center;color:#A39E96;font-size:14px')}>No call has been completed yet for this episode.</div>
                    )}
                  </div>

                  {/* FACE-TO-FACE VISIT */}
                  {sel.hasVisit && (
                    <div style={css('padding-bottom:4px')}>
                      <SectionHeader>Face-to-face visit</SectionHeader>
                      <div style={css('display:flex;align-items:center;gap:13px')}>
                        <div>
                          <div style={css('font-weight:700;font-size:16px')}>{sel.visitSlot}</div>
                          <div style={css('font-size:13px;color:#9A968F;margin-top:1px')}>{sel.visitProvider}</div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* BILLING INFO */}
                  {sel.hasCode && (
                    <div style={css('padding-bottom:4px')}>
                      <SectionHeader>Billing info</SectionHeader>
                      <div style={css('font-size:13px;line-height:1.5;color:#6B6770;margin-bottom:14px')}>ContinuaCare recommends <b style={{ color: '#032640' }}>{sel.recCode}</b> from the call. Confirm it, or override with the other code.</div>
                      <div style={css('display:flex;flex-direction:column;gap:10px;margin-bottom:14px')}>
                        {sel.codeOptions.map((o) => (
                          <div key={o.code} onClick={() => !o.disabled && chooseCode(sel.id, o.code)} style={o.rowStyle}>
                            <div style={css('display:flex;align-items:center;gap:13px')}>
                              <span style={o.radioStyle}>{o.radioMark}</span>
                              <div>
                                <div style={css('display:flex;align-items:center;gap:9px')}>
                                  <span className="disp" style={css('font-size:19px;font-weight:700')}>{o.code}</span>
                                  {o.isRec && <span style={css('background:#EAF0F5;color:#032640;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;text-transform:uppercase;letter-spacing:0.03em')}>Recommended</span>}
                                </div>
                                <div style={css('font-size:12.5px;color:#6B6770;margin-top:1px')}>{o.complexity} · {o.amount}</div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                      <div style={css('font-size:13px;line-height:1.45;color:#6B6770;margin-bottom:14px')}>{sel.codeRationale}</div>
                      {sel.codePending && (
                        <H as="button" onClick={() => confirmCode(sel.id)} style={css('width:100%;background:#032640;color:#fff;border:none;font-weight:600;font-size:14px;padding:13px;border-radius:8px;cursor:pointer')} hoverStyle={{ background: '#0a3a5c' }}>{sel.confirmCodeBtn}</H>
                      )}
                      {sel.codeConfirmed && (
                        <div style={css('background:rgba(14,154,73,0.1);border:1px solid rgba(14,154,73,0.55);border-radius:8px;padding:13px 16px;font-size:14px;font-weight:600;color:#0E9A49;display:flex;align-items:center;gap:8px')}>✓ {sel.confirmedText}</div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </aside>
          </>
        )}
      </div>

      {/* ===== DISCHARGE MODAL ===== */}
      {dischargeModal && (
        <div style={css('position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:100;display:flex;align-items:center;justify-content:center;padding:24px')}>
          <div style={css('background:#fff;border-radius:14px;width:100%;max-width:480px;padding:28px;box-shadow:0 8px 40px rgba(0,0,0,0.18)')}>
            <div style={css('display:flex;align-items:center;justify-content:space-between;margin-bottom:20px')}>
              <div>
                <div className="disp" style={css('font-size:19px;font-weight:700')}>Initiate Discharge</div>
                <div style={css('font-size:13px;color:#9A968F;margin-top:2px')}>{dischargeModal.patientName}</div>
              </div>
              <H as="button" onClick={closeDischargeModal} style={css('width:32px;height:32px;border-radius:7px;border:1px solid rgba(26,26,30,0.12);background:#fff;color:#6B6770;font-size:14px;cursor:pointer')} hoverStyle={{ background: 'rgba(26,26,30,0.06)' }}>✕</H>
            </div>

            <div style={css('display:flex;flex-direction:column;gap:16px')}>
              <div>
                <div style={css('font-size:12px;font-weight:700;letter-spacing:0.03em;text-transform:uppercase;color:#A39E96;margin-bottom:6px')}>Discharge date & time</div>
                <input
                  type="datetime-local"
                  value={dischargeDate}
                  onChange={(e) => setDischargeDate(e.target.value)}
                  style={css('width:100%;border:1px solid rgba(26,26,30,0.18);border-radius:8px;padding:10px 12px;font-size:14px;outline:none;box-sizing:border-box')}
                />
              </div>
              <div>
                <div style={css('font-size:12px;font-weight:700;letter-spacing:0.03em;text-transform:uppercase;color:#A39E96;margin-bottom:6px')}>Discharge notes</div>
                <textarea
                  rows={5}
                  placeholder="Enter discharge diagnosis, relevant history, medications, and instructions..."
                  value={dischargeNotes}
                  onChange={(e) => setDischargeNotes(e.target.value)}
                  style={css('width:100%;border:1px solid rgba(26,26,30,0.18);border-radius:8px;padding:10px 12px;font-size:14px;line-height:1.5;resize:vertical;outline:none;box-sizing:border-box;font-family:inherit')}
                />
              </div>
              <div style={css('font-size:12.5px;color:#9A968F;line-height:1.45')}>
                This will create a TCM episode and automatically schedule a follow-up call to the patient within 15 seconds.
              </div>
              {submitError && (
                <div style={css('background:rgba(229,51,31,0.1);border:1px solid rgba(229,51,31,0.4);border-radius:8px;padding:10px 14px;font-size:13px;color:#C42718')}>{submitError}</div>
              )}
              <div style={css('display:flex;gap:10px;justify-content:flex-end;margin-top:4px')}>
                <H as="button" onClick={closeDischargeModal} style={css('padding:10px 18px;border:1px solid rgba(26,26,30,0.15);border-radius:8px;background:#fff;font-size:14px;font-weight:600;color:#6B6770;cursor:pointer')} hoverStyle={{ background: '#f5f5f5' }}>Cancel</H>
                <H
                  as="button"
                  onClick={handleDischargeSubmit}
                  style={css(`padding:10px 20px;border:none;border-radius:8px;background:${submitting || !dischargeNotes.trim() ? '#9ca3af' : '#032640'};color:#fff;font-size:14px;font-weight:600;cursor:${submitting || !dischargeNotes.trim() ? 'not-allowed' : 'pointer'}`)}
                  hoverStyle={submitting || !dischargeNotes.trim() ? {} : { background: '#0a3a5c' }}
                >
                  {submitting ? 'Creating…' : 'Initiate discharge & schedule call'}
                </H>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
