import { useEffect, useRef, useState } from 'react'
import { Room, RoomEvent, Track, RemoteParticipant, ParticipantEvent, RemoteTrackPublication } from 'livekit-client'
import { css, H } from '../lib/ui'

interface Props {
  token: string
  wsUrl: string
  patientName: string
  onClose: () => void
}

type CallState = 'connecting' | 'waiting' | 'active' | 'ended'

export default function WebCallOverlay({ token, wsUrl, patientName, onClose }: Props) {
  const roomRef = useRef<Room | null>(null)
  const audioContainerRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<CallState>('connecting')
  const [agentSpeaking, setAgentSpeaking] = useState(false)
  const [muted, setMuted] = useState(false)
  const [duration, setDuration] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const room = new Room()
    roomRef.current = room

    // Attach a remote audio track to a real <audio> element so the browser plays it
    const attachAudio = (publication: RemoteTrackPublication) => {
      if (publication.kind !== Track.Kind.Audio || !publication.track) return
      const el = publication.track.attach()
      el.autoplay = true
      audioContainerRef.current?.appendChild(el)
    }

    const onAgentJoined = (participant: RemoteParticipant) => {
      setState('active')
      if (!timerRef.current) {
        timerRef.current = setInterval(() => setDuration((d) => d + 1), 1000)
      }
      participant.on(ParticipantEvent.IsSpeakingChanged, (speaking: boolean) => {
        setAgentSpeaking(speaking)
      })
      // Attach any tracks already published
      for (const pub of participant.audioTrackPublications.values()) {
        attachAudio(pub)
      }
    }

    room.on(RoomEvent.ParticipantConnected, onAgentJoined)

    room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
      if (track.kind === Track.Kind.Audio) {
        attachAudio(publication as RemoteTrackPublication)
        participant.on(ParticipantEvent.IsSpeakingChanged, (speaking: boolean) => {
          setAgentSpeaking(speaking)
        })
      }
    })

    // Handle agent already in room when we connect
    room.on(RoomEvent.Connected, () => {
      for (const p of room.remoteParticipants.values()) {
        onAgentJoined(p)
      }
    })

    room.on(RoomEvent.ParticipantDisconnected, () => {
      setState('ended')
      if (timerRef.current) clearInterval(timerRef.current)
    })

    room.on(RoomEvent.Disconnected, () => {
      setState('ended')
      if (timerRef.current) clearInterval(timerRef.current)
    })

    room
      .connect(wsUrl, token, { autoSubscribe: true })
      .then(async () => {
        setState('waiting')
        await room.startAudio()
        await room.localParticipant.setMicrophoneEnabled(true)
      })
      .catch((err) => {
        console.error('LiveKit connect failed', err)
        setState('ended')
      })

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      // Detach all audio elements
      if (audioContainerRef.current) {
        audioContainerRef.current.innerHTML = ''
      }
      room.disconnect()
    }
  }, [token, wsUrl])

  const toggleMute = async () => {
    const room = roomRef.current
    if (!room) return
    const enabled = room.localParticipant.isMicrophoneEnabled
    await room.localParticipant.setMicrophoneEnabled(!enabled)
    setMuted(enabled)
  }

  const endCall = () => {
    roomRef.current?.disconnect()
    setState('ended')
    if (timerRef.current) clearInterval(timerRef.current)
    setTimeout(onClose, 1200)
  }

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

  return (
    <div style={css('position:fixed;inset:0;background:rgba(3,38,64,0.88);z-index:200;display:flex;align-items:center;justify-content:center')}>
      {/* Hidden audio container — LiveKit attaches <audio> elements here */}
      <div ref={audioContainerRef} style={{ display: 'none' }} />

      <div style={css('background:#fff;border-radius:20px;width:100%;max-width:380px;padding:36px 32px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,0.35);position:relative')}>
        <H as="button" onClick={onClose} style={css('position:absolute;top:14px;right:14px;width:30px;height:30px;border-radius:7px;border:1px solid rgba(26,26,30,0.12);background:#fff;color:#6B6770;font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center')} hoverStyle={{ background: 'rgba(26,26,30,0.06)' }}>✕</H>

        {/* Avatar */}
        <div style={css('width:80px;height:80px;border-radius:50%;background:#032640;margin:0 auto 18px;display:flex;align-items:center;justify-content:center;position:relative')}>
          <span style={css('font-size:32px')}>🩺</span>
          {agentSpeaking && (
            <span style={css('position:absolute;inset:-4px;border-radius:50%;border:3px solid #0E9A49;animation:pulse 1s ease-in-out infinite')} />
          )}
        </div>

        <div className="disp" style={css('font-size:22px;font-weight:700;color:#032640;margin-bottom:4px')}>Aria</div>
        <div style={css('font-size:13px;color:#9A968F;margin-bottom:6px')}>ContinuaCare AI · follow-up call with {patientName}</div>

        {/* Status */}
        <div style={css('font-size:13px;font-weight:600;margin-bottom:24px;' + (
          state === 'connecting' ? 'color:#9A968F' :
          state === 'waiting' ? 'color:#E0A211' :
          state === 'active' ? 'color:#0E9A49' :
          'color:#E5331F'
        ))}>
          {state === 'connecting' && '⏳ Connecting…'}
          {state === 'waiting' && '⌛ Waiting for Aria…'}
          {state === 'active' && (agentSpeaking ? '🔊 Aria is speaking' : `✓ Connected · ${fmt(duration)}`)}
          {state === 'ended' && '✓ Call ended'}
        </div>

        {/* Controls */}
        {state !== 'ended' && (
          <div style={css('display:flex;align-items:center;justify-content:center;gap:18px')}>
            <H
              as="button"
              onClick={toggleMute}
              style={css(`width:54px;height:54px;border-radius:50%;border:2px solid ${muted ? '#E5331F' : 'rgba(26,26,30,0.15)'};background:${muted ? 'rgba(229,51,31,0.08)' : '#fff'};font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center`)}
              hoverStyle={{ background: muted ? 'rgba(229,51,31,0.14)' : 'rgba(26,26,30,0.06)' }}
              title={muted ? 'Unmute' : 'Mute'}
            >
              {muted ? '🔇' : '🎙️'}
            </H>

            <H
              as="button"
              onClick={endCall}
              style={css('width:64px;height:64px;border-radius:50%;border:none;background:#E5331F;color:#fff;font-size:26px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(229,51,31,0.35)')}
              hoverStyle={{ background: '#C42718' }}
              title="End call"
            >
              📵
            </H>
          </div>
        )}

        {state === 'ended' && (
          <div style={css('display:flex;flex-direction:column;align-items:center;gap:14px')}>
            <div style={css('font-size:13px;color:#9A968F')}>The transcript will appear in the care console shortly.</div>
            <H as="button" onClick={onClose} style={css('padding:9px 22px;border:1px solid rgba(26,26,30,0.15);border-radius:8px;background:#fff;font-size:14px;font-weight:600;color:#6B6770;cursor:pointer')} hoverStyle={{ background: '#f5f5f5' }}>Close</H>
          </div>
        )}

        <style>{`
          @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.08); }
          }
        `}</style>
      </div>
    </div>
  )
}
