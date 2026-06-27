import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { css, H } from '../lib/ui'

const SECTIONS = ['top', 'problem', 'numbers', 'workflow'] as const
type SectionId = (typeof SECTIONS)[number]

/** Internal Link to the demo console with a hover style (replaces DCLogic style-hover). */
function DemoLink({
  style,
  hoverStyle,
  children,
}: {
  style: React.CSSProperties
  hoverStyle: React.CSSProperties
  children: React.ReactNode
}) {
  const [h, setH] = useState(false)
  return (
    <Link
      to="/demo"
      style={{ ...style, ...(h ? hoverStyle : {}) }}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
    >
      {children}
    </Link>
  )
}

export default function Landing() {
  const [active, setActive] = useState<SectionId>('top')
  const scrollerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const root = scrollerRef.current
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) setActive(e.target.id as SectionId)
        })
      },
      { root, rootMargin: '-48% 0px -48% 0px', threshold: 0 }
    )
    SECTIONS.forEach((id) => {
      const el = document.getElementById(id)
      if (el) io.observe(el)
    })
    return () => io.disconnect()
  }, [])

  const dot = (id: SectionId): React.CSSProperties => {
    const on = active === id
    return {
      width: '6px',
      borderRadius: '100px',
      height: on ? '26px' : '8px',
      background: on ? '#032640' : 'rgba(3,38,64,0.2)',
      transition: 'height .25s, background .25s',
    }
  }

  return (
    <div className="cc-landing" ref={scrollerRef} style={{ background: '#F6F6F8' }}>
      {/* ===== VERTICAL PILL NAV ===== */}
      <div
        style={css(
          'position:fixed;left:20px;top:50%;transform:translateY(-50%);z-index:60;display:flex;flex-direction:column;align-items:center;gap:16px;background:rgba(255,255,255,0.9);backdrop-filter:blur(12px);border:1px solid rgba(3,38,64,0.1);border-radius:100px;padding:14px 8px;box-shadow:0 10px 34px rgba(3,38,64,0.12)'
        )}
      >
        {(
          [
            ['top', 'Home'],
            ['problem', 'The problem'],
            ['numbers', 'Size of the gap'],
            ['workflow', 'The solution'],
          ] as [SectionId, string][]
        ).map(([id, label]) => (
          <a key={id} href={`#${id}`} className="navdot">
            <span style={dot(id)} />
            <span className="navlabel">{label}</span>
          </a>
        ))}
      </div>

      {/* ===== SECTION 1 · HERO ===== */}
      <section
        id="top"
        style={css(
          'min-height:100vh;width:100%;background:linear-gradient(165deg,#EAF0F5 0%,#F6F6F8 45%,#E8F5EC 100%);display:flex;flex-direction:column;justify-content:center;padding:80px max(96px, calc(50vw - 590px)) 60px;position:relative'
        )}
      >
        <DemoLink
          style={css('position:absolute;top:34px;left:max(40px, calc(50vw - 590px));display:flex;align-items:center;gap:10px')}
          hoverStyle={{ opacity: 0.75 }}
        >
          <div style={css('width:30px;height:30px;border-radius:9px;background:#032640;display:flex;align-items:center;justify-content:center;gap:2.5px')}>
            <span style={css('width:2.5px;height:8px;border-radius:2px;background:#7FD3A5')} />
            <span style={css('width:2.5px;height:13px;border-radius:2px;background:#fff')} />
            <span style={css('width:2.5px;height:10px;border-radius:2px;background:#2FB76C')} />
          </div>
          <span className="disp" style={css('font-size:20px;font-weight:700')}>Continua</span>
        </DemoLink>

        <div style={css('width:100%;max-width:1180px;margin:0 auto;display:grid;grid-template-columns:1.05fr 0.95fr;gap:48px;align-items:center')}>
          <div>
            <h1 className="disp" style={css('font-size:48px;font-weight:700;margin-bottom:24px;letter-spacing:-0.03em')}>
              Better recovery.<br />Fewer readmissions.<br />More revenue.
            </h1>
            <p style={css('font-size:19px;line-height:1.55;color:#54515B;max-width:490px;margin-bottom:34px')}>
              Continua is the <b style={{ color: '#032640' }}>agentic AI care coordinator</b> that automates Transitional Care Management for primary care practices. After every hospital discharge, it calls the patient, screens for red flags, books the follow-up visit, and captures Medicare billing.
            </p>
            <div style={css('display:flex;align-items:center;gap:18px')}>
              <DemoLink
                style={css('display:flex;align-items:center;gap:11px;background:#032640;color:#fff;font-weight:600;font-size:16px;padding:15px 16px 15px 26px;border-radius:100px')}
                hoverStyle={{ background: '#0a3a5c' }}
              >
                Open the live demo
                <span style={css('display:inline-flex;width:30px;height:30px;border-radius:50%;background:#0E9A49;color:#fff;align-items:center;justify-content:center;font-size:16px')}>→</span>
              </DemoLink>
            </div>
          </div>

          <div style={css('display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:14px;height:466px')}>
            {/* Episode + TCM pipeline */}
            <div style={css('grid-row:span 2;background:#fff;border:1px solid rgba(26,26,30,0.1);border-radius:16px;padding:20px;display:flex;flex-direction:column')}>
              <div style={css('display:flex;align-items:center;gap:10px')}>
                <div style={css('width:34px;height:34px;border-radius:10px;background:#EAF0F5;color:#032640;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;flex-shrink:0')}>EW</div>
                <div>
                  <div style={css('font-weight:700;font-size:14px;line-height:1.1')}>Eleanor Whitfield</div>
                  <div style={css('font-size:11.5px;color:#8A8792;margin-top:1px')}>74 · Heart failure</div>
                </div>
              </div>
              <div style={css('flex:1;display:flex;flex-direction:column;justify-content:center')}>
                {[
                  { label: 'Contact', sub: 'Reached · Day 1', done: true },
                  { label: 'Visit', sub: 'Booked · Day 7', done: true },
                  { label: 'Billing', sub: 'Claim ready · Day 30', done: false },
                ].map((st, i, arr) => (
                  <div key={st.label} style={{ display: 'flex', gap: '11px', minHeight: i < arr.length - 1 ? '50px' : 'auto' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{ width: '22px', height: '22px', borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '11px', background: st.done ? '#032640' : '#fff', border: st.done ? 'none' : '2px solid #032640', color: st.done ? '#fff' : '#032640' }}>
                        {st.done ? '✓' : ''}
                      </div>
                      {i < arr.length - 1 && <div style={{ width: '2px', flex: 1, margin: '4px 0', background: '#032640' }} />}
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: '13.5px', color: '#032640', lineHeight: 1.1 }}>{st.label}</div>
                      <div style={{ fontSize: '11.5px', color: '#9A968F', marginTop: '2px' }}>{st.sub}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Safety catch */}
            <div style={css('background:#fff;border:1px solid rgba(26,26,30,0.1);border-radius:16px;padding:18px;display:flex;flex-direction:column;justify-content:space-between')}>
              <div style={css('display:flex;align-items:center;gap:7px;font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;color:#E5331F')}>
                <span style={css('width:7px;height:7px;border-radius:50%;background:#E5331F;animation:blink 1.4s infinite')} /> Flagged
              </div>
              <div>
                <div className="disp" style={css('font-size:16px;font-weight:700;line-height:1.15;margin-bottom:4px')}>“My fever’s back.”</div>
                <div style={css('font-size:11.5px;color:#6B6770;line-height:1.4')}>Caught mid-call, a nurse is alerted in seconds.</div>
              </div>
            </div>

            {/* Live call (kept) */}
            <div style={css('background:#032640;border-radius:16px;padding:18px;color:#fff;display:flex;flex-direction:column;justify-content:space-between')}>
              <div style={css('display:flex;align-items:center;gap:8px;font-size:11.5px;color:#7FD3A5;font-weight:600')}>
                <span style={css('width:7px;height:7px;border-radius:50%;background:#2FB76C;animation:blink 1.4s infinite')} /> CALL · LIVE
              </div>
              <div style={css('display:flex;align-items:flex-end;gap:3px;height:28px;margin:10px 0')}>
                {[
                  '40%', '80%', '55%', '100%', '65%', '35%', '75%',
                ].map((h, i) => (
                  <span key={i} style={{ width: '3px', borderRadius: '2px', background: ['#2FB76C', '#7FD3A5', '#fff'][i % 3], height: h }} />
                ))}
              </div>
              <div style={css('font-size:12px;color:#B7B4BE;line-height:1.35')}>“Would Thursday at 9:40 work for your visit?”</div>
            </div>

            {/* Claim ready */}
            <div style={css('background:#fff;border:1px solid rgba(26,26,30,0.1);border-radius:16px;padding:18px 20px;grid-column:span 2;display:flex;align-items:center;justify-content:space-between;gap:16px')}>
              <div style={css('display:flex;align-items:center;gap:13px;min-width:0')}>
                <div style={css('width:44px;height:44px;border-radius:12px;background:#EAF0F5;color:#032640;display:flex;align-items:center;justify-content:center;flex-shrink:0')}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="m9 15 2 2 4-4" /></svg>
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={css('font-weight:700;font-size:15px;line-height:1.1')}>Claim packet ready</div>
                  <div style={css('font-size:12px;color:#6B6770;margin-top:2px')}>CPT 99496 · High-complexity TCM</div>
                </div>
              </div>
              <div style={css('display:flex;align-items:center;gap:14px;flex-shrink:0')}>
                <div className="disp" style={css('font-size:24px;font-weight:700;color:#032640')}>$272.68</div>
                <div style={css('display:inline-flex;align-items:center;gap:6px;background:#E8F5EC;color:#0E9A49;font-weight:700;font-size:12px;padding:6px 12px;border-radius:100px;white-space:nowrap')}>✓ Ready to bill</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== SECTION 2 · PROBLEM ===== */}
      <section id="problem" style={css('min-height:100vh;width:100%;background:#FFFFFF;display:flex;flex-direction:column;justify-content:center;padding:64px max(96px, calc(50vw - 590px))')}>
        <div style={css('width:100%;max-width:1180px;margin:0 auto')}>
          <div style={{ maxWidth: '820px' }}>
            <div style={css('font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0E9A49;margin-bottom:18px')}>Understanding Transitional Care Management (TCM)</div>
            <h2 className="disp" style={css('font-size:38px;font-weight:700;line-height:1.12;margin-bottom:20px;letter-spacing:-0.02em')}>TCM is a Medicare program that pays primary care physicians $200–$275 per patient to coordinate care in the 30 days following a hospital discharge.</h2>
            <p style={css('font-size:18px;line-height:1.6;color:#54515B')}>The weeks after discharge carry the highest risk of readmission — yet <b style={{ color: '#032640' }}>1 in 5 Medicare patients</b> is readmitted within 30 days, and only half ever get a follow-up visit with their doctor. The process is entirely manual, and most small practices have no one dedicated to it.</p>
          </div>

          <div style={css('margin-top:28px;border:1px solid rgba(26,26,30,0.1);border-radius:18px;padding:26px 36px')}>
            <div style={css('display:grid;grid-template-columns:repeat(3,1fr);gap:24px;position:relative')}>
              <div style={css('position:absolute;top:17px;left:18px;right:calc(33.333% - 34px);height:2px;background:linear-gradient(90deg,#2FB76C,#032640 55%,#D98686)')} />
              {[
                { color: '#0E9A49', icon: <path d="M3 21h18M5 21V8l7-5 7 5v13M9 21v-5h6v5" />, t: 'A patient comes home', p: 'New medications, new instructions, and the highest readmission risk of the whole recovery.' },
                { color: '#032640', icon: <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z" />, t: 'Someone must follow up, by hand', p: 'Call and screen the patient, book the visit, document it, on whoever has a spare minute.' },
                { color: '#C0473F', icon: <><circle cx="12" cy="12" r="9" /><path d="M15 9l-6 6M9 9l6 6" /></>, t: 'So it falls through', p: 'The check-in never happens, the patient goes unseen, and the payment is forfeited.' },
              ].map((s, i) => (
                <div key={i} style={{ position: 'relative' }}>
                  <div style={{ ...css('width:36px;height:36px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;margin-bottom:18px;position:relative;z-index:1'), border: '2px solid ' + s.color, color: s.color }}>
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">{s.icon}</svg>
                  </div>
                  <div style={css('font-weight:700;font-size:16px;margin-bottom:6px')}>{s.t}</div>
                  <p style={css('font-size:14px;line-height:1.5;color:#6B6770')}>{s.p}</p>
                </div>
              ))}
            </div>
          </div>

        </div>
      </section>

      {/* ===== SECTION 3 · STAKES ===== */}
      <section id="numbers" style={css('min-height:100vh;width:100%;background:#F6F6F8;display:flex;flex-direction:column;justify-content:center;padding:44px max(96px, calc(50vw - 590px))')}>
        <div style={css('width:100%;max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:12px')}>
          <div>
            <div style={css('font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0E9A49;margin-bottom:14px')}>The problem</div>
            <h2 className="disp" style={css('font-size:42px;font-weight:700;line-height:1.05;letter-spacing:-0.02em')}>Over two billion dollars,<br />left on the table.</h2>
          </div>

          <div style={css('display:grid;grid-template-columns:repeat(3,1fr);border:1px solid rgba(26,26,30,0.1);border-radius:18px;overflow:hidden;background:#fff')}>
            {[
              { v: '3 in 4', c: undefined, d: 'practices have no dedicated care coordinator', dark: false },
              { v: '85%', c: '#0E9A49', d: 'of eligible discharges go unbilled nationally', dark: false },
              { v: '$2.25B', c: '#7FD3A5', d: 'left unclaimed every year, Medicare alone', dark: true },
            ].map((cell, i) => (
              <div key={i} style={{ padding: '22px 26px', borderRight: i < 2 ? '1px solid rgba(26,26,30,0.1)' : undefined, background: cell.dark ? '#032640' : undefined }}>
                <div className="disp" style={{ fontSize: '40px', fontWeight: 700, color: cell.c }}>{cell.v}</div>
                <div style={{ fontSize: '14px', color: cell.dark ? '#C2BFC9' : '#6B6770', lineHeight: 1.45, marginTop: '8px' }}>{cell.d}</div>
              </div>
            ))}
          </div>

          <div style={css('display:grid;grid-template-columns:1fr 1fr;gap:12px')}>
            <div style={css('border:1px solid rgba(26,26,30,0.1);border-radius:18px;padding:22px 28px')}>
              <div className="disp" style={css('font-size:22px;font-weight:600;line-height:1.12;margin-bottom:10px')}>No one owns the follow-up.</div>
              <p style={css('font-size:14px;line-height:1.55;color:#54515B')}>Most small practices have no dedicated care coordinator and can't afford to hire one. So discharge follow-up is done by hand, squeezed between phones, rooming, and everything else.</p>
            </div>
            <div style={css('background:#032640;border-radius:18px;padding:22px 28px;color:#fff')}>
              <div className="disp" style={css('font-size:22px;font-weight:600;line-height:1.12;margin-bottom:10px;color:#7FD3A5')}>Patients go unseen. Revenue is forfeited.</div>
              <p style={css('font-size:14px;line-height:1.55;color:#C2BFC9')}>When the team is at capacity, follow-up is the first thing to drop. Patients miss the check-in that prevents readmissions, and the practice forfeits the Medicare payment it earned.</p>
            </div>
          </div>

          <div style={css('border:1px solid rgba(29,79,215,0.28);background:#EAF0F5;border-radius:18px;padding:22px 32px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:20px')}>
            <div style={{ maxWidth: '580px' }}>
              <div className="disp" style={css('font-size:21px;font-weight:600;margin-bottom:6px')}>What this means for a single primary care practice</div>
              <p style={css('font-size:14px;line-height:1.55;color:#54515B')}>A four-physician practice seeing roughly 16 TCM-eligible discharges a month leaves approximately <b style={{ color: '#032640' }}>$45,000 a year</b> uncaptured.</p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div className="disp" style={css('font-size:46px;font-weight:700;color:#032640')}>~$45k</div>
              <div style={css('font-size:13px;color:#41566B;font-weight:500')}>per practice / year, recovered</div>
            </div>
          </div>

          <p style={css('font-size:11px;color:#A8A4AC;line-height:1.5')}>* Estimates derived from national Medicare TCM utilization rates and average reimbursement per episode.</p>
        </div>
      </section>

      {/* ===== SECTION 4 · WORKFLOW ===== */}
      <section id="workflow" style={css('min-height:100vh;width:100%;background:#FFFFFF;display:flex;flex-direction:column;padding:48px max(96px, calc(50vw - 590px))')}>
        <div style={css('flex:1;width:100%;max-width:1180px;margin:0 auto;display:flex;flex-direction:column;justify-content:center')}>
          <div style={css('max-width:880px;margin-bottom:24px')}>
            <div style={css('font-size:13px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#0E9A49;margin-bottom:16px')}>How Continua works</div>
            <h2 className="disp" style={css('font-size:46px;font-weight:700;line-height:1.05;margin-bottom:16px;letter-spacing:-0.02em;white-space:nowrap')}>Automate transition of care to put<br />Medicare dollars back in your wallet.</h2>
            <p style={css('font-size:18px;line-height:1.6;color:#54515B')}>The moment a discharge is known, Continua's AI agent runs the whole pipeline, and pulls in a human only when it's truly needed.</p>
          </div>

          <div style={css('display:grid;grid-template-columns:repeat(5,1fr);gap:14px')}>
            {[
              { t: 'Discharge fires', p: 'The hospital notice lands and the patient record fills in automatically.' },
              { t: 'Continua calls', p: 'The agent phones the patient, symptom check, meds, and scheduling, on script.' },
              { t: 'Flags a human', p: 'Concerning answers hand off to a human, live, or flagged for a callback.' },
              { t: 'Schedules visit', p: 'The visit is scheduled, and 99495 or 99496 is proposed for the provider to confirm.' },
              { t: 'Ready to bill', p: 'After 30 days, the episode is ready, fully documented and coded.' },
            ].map((step, i) => (
              <div key={i} style={css('background:#F1F1F3;border-radius:14px;padding:18px 20px')}>
                <div style={css('width:30px;height:30px;border-radius:50%;background:#0E9A49;color:#fff;display:flex;align-items:center;justify-content:center;font-family:monospace;font-size:13px;font-weight:700;margin-bottom:16px')}>{i + 1}</div>
                <div style={css('font-weight:700;font-size:15.5px;margin-bottom:8px')}>{step.t}</div>
                <p style={css('font-size:13.5px;line-height:1.5;color:#6B6770')}>{step.p}</p>
              </div>
            ))}
          </div>

          {/* CTA band */}
          <div style={css('margin-top:22px;background:#032640;border-radius:24px;padding:30px 40px;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:28px')}>
            <div style={css('position:absolute;right:-60px;top:-60px;width:240px;height:240px;border-radius:50%;background:#0E9A49;opacity:0.22;filter:blur(20px)')} />
            <div style={css('position:relative;max-width:560px')}>
              <h2 className="disp" style={css('font-size:30px;font-weight:700;color:#fff;line-height:1.08;margin-bottom:10px;letter-spacing:-0.02em')}>See Continua close an episode, live.</h2>
              <p style={css('font-size:16px;line-height:1.5;color:#C2BFC9')}>Trigger a discharge and watch it call the patient, flag a human, book the visit, and hand back a billable episode.</p>
            </div>
            <DemoLink
              style={css('position:relative;display:inline-flex;align-items:center;gap:12px;background:#fff;color:#032640;font-weight:700;font-size:16px;padding:15px 18px 15px 26px;border-radius:100px;white-space:nowrap')}
              hoverStyle={{ background: '#E8F5EC' }}
            >
              Open the live demo
              <span style={css('display:inline-flex;width:30px;height:30px;border-radius:50%;background:#0E9A49;color:#fff;align-items:center;justify-content:center;font-size:15px')}>→</span>
            </DemoLink>
          </div>
        </div>

        <div style={css('width:100%;max-width:1180px;margin:0 auto')}>
          <div style={css('display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:14px;border-top:1px solid rgba(26,26,30,0.08);padding-top:16px')}>
            <div style={css('display:flex;align-items:center;gap:10px')}>
              <div style={css('width:26px;height:26px;border-radius:7px;background:#032640;display:flex;align-items:center;justify-content:center;gap:2px')}>
                <span style={css('width:2.5px;height:7px;border-radius:2px;background:#7FD3A5')} />
                <span style={css('width:2.5px;height:12px;border-radius:2px;background:#fff')} />
                <span style={css('width:2.5px;height:9px;border-radius:2px;background:#2FB76C')} />
              </div>
              <span className="disp" style={css('font-size:17px;font-weight:700')}>Continua</span>
              <span style={css('font-size:13px;color:#8A8792;margin-left:6px')}>Autonomous transitional care</span>
            </div>
            <div style={css('font-size:13px;color:#8A8792')}>A hackathon demo · not for clinical use</div>
          </div>
        </div>
      </section>
    </div>
  )
}
