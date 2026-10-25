'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

interface Place {
  place_id?: string;
  name?: string;
  category?: string;
  rating?: number;
  reviews?: number;
  address?: string;
  thumbnail?: string;
}

interface Member {
  id: string;
  name: string;
  is_host: boolean;
  done: boolean;
  answered: number;
  voted: boolean;
}

interface RoomState {
  room_id: string;
  code: string;
  city: string;
  status: 'lobby' | 'answering' | 'searching' | 'voting' | 'done';
  message: string | null;
  questions_per_member: number;
  me: { id: string; name: string; is_host: boolean; done: boolean; answered: number; vote: number | null };
  members: Member[];
  results: {
    place: Place;
    reason: string;
    votes: number;
    per_person?: { name: string; why: string }[];
    based_on?: string[];
  }[];
  winner: number | null;
}

interface Question {
  question: string;
  options: string[];
  placeholder?: string;
  number?: number;
}

const POLL_MS = 2000;

// sessionStorage never changes under us, so there's nothing to subscribe to.
const noSubscribe = () => () => {};

function readToken(roomId: string): string | null {
  try {
    return sessionStorage.getItem(`findmyvibe:member:${roomId}`);
  } catch {
    return null;
  }
}

const card = 'relative z-10 w-full max-w-3xl bg-[#fcf8f0]/95 border-2 border-[#bfa27b] rounded-3xl p-6 sm:p-10 shadow-[0_15px_40px_rgba(120,70,30,0.2)]';
const primaryBtn = 'w-full py-4 bg-gradient-to-r from-[#8b4f26] via-[#a35e2e] to-[#8b4f26] hover:from-[#75411d] hover:to-[#75411d] font-sans font-bold text-sm tracking-wider uppercase rounded-xl transition shadow-lg shadow-amber-900/20 text-[#fcf8f0] border border-[#d4a86a] cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed';
const secondaryBtn = 'w-full py-3 bg-[#f3e7d3] hover:bg-[#ead6b8] text-[#59391e] font-sans font-bold text-sm tracking-wider uppercase rounded-xl border border-[#cbaf8b] transition cursor-pointer disabled:opacity-40';

function mapsLink(place: Place, city: string) {
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${place.name || ''} ${place.address || city}`)}`;
}

export default function GroupRoom() {
  const params = useParams<{ roomId: string }>();
  const roomId = decodeURIComponent(params.roomId);
  // The private member token saved when you created or joined this party
  // (undefined while rendering on the server).
  const token = useSyncExternalStore<string | null | undefined>(
    noSubscribe,
    () => readToken(roomId),
    () => undefined
  );
  const [room, setRoom] = useState<RoomState | null>(null);
  const [fatal, setFatal] = useState('');
  const [actionErrorAt, setActionErrorAt] = useState<{ message: string; status: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [question, setQuestion] = useState<Question | null>(null);
  const [custom, setCustom] = useState('');
  const [copied, setCopied] = useState(false);
  const fetchingQuestion = useRef(false);

  const call = useCallback(
    async (path: string, method: 'GET' | 'POST' = 'GET', body?: unknown) => {
      const res = await fetch(`/api/groups/${encodeURIComponent(roomId)}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', 'X-Member-Token': token || '' },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 429) {
        throw new Error('Puss needs a catnap! Too many requests. Try again in a minute.');
      }
      if (!res.ok) {
        const err = new Error(data.detail || `Request failed (${res.status})`) as Error & { status?: number };
        err.status = res.status;
        throw err;
      }
      return data;
    },
    [roomId, token]
  );

  // Keep the room in sync for everyone.
  const refresh = useCallback(async () => {
    try {
      setRoom(await call(''));
    } catch (e) {
      const err = e as Error & { status?: number };
      if (err.status === 401 || err.status === 404) setFatal(err.message);
    }
  }, [call]);

  useEffect(() => {
    if (!token) return;
    const first = setTimeout(refresh, 0);
    const id = setInterval(() => {
      if (room?.status !== 'done') refresh();
    }, POLL_MS);
    return () => { clearTimeout(first); clearInterval(id); };
  }, [token, refresh, room?.status]);

  // Fetch my next question when it's my turn to answer.
  useEffect(() => {
    if (!room || room.status !== 'answering' || room.me.done || question || fetchingQuestion.current) return;
    fetchingQuestion.current = true;
    call('/turn', 'POST', {})
      .then((q) => { if (!q.done) setQuestion(q); else refresh(); })
      // 409 = the party already moved on (e.g. voting opened); just catch up.
      .catch((e) => { if ((e as { status?: number }).status === 409) refresh(); else setActionErrorAt({ message: (e as Error).message, status: room.status }); })
      .finally(() => { fetchingQuestion.current = false; });
  }, [room, question, call, refresh]);

  const act = async (path: string, body?: unknown) => {
    setBusy(true);
    setActionErrorAt(null);
    try {
      const data = await call(path, 'POST', body ?? {});
      if (data && data.status) setRoom(data);
      return data;
    } catch (e) {
      setActionErrorAt({ message: (e as Error).message, status: room?.status || '' });
    } finally {
      setBusy(false);
    }
  };

  const answer = async (text: string) => {
    if (!question || busy || !text.trim()) return;
    const next = await act('/turn', { question: question.question, answer: text.trim() });
    if (!next) return;
    setCustom('');
    setQuestion(next.done ? null : next);
    if (next.done) {
      // Mark myself done right away so we don't ask for another question
      // before the next poll catches up.
      setRoom((prev) => prev && { ...prev, me: { ...prev.me, done: true, answered: prev.questions_per_member } });
      refresh();
    }
  };

  const copyInvite = async () => {
    if (!room) return;
    const link = `${window.location.origin}/group?code=${encodeURIComponent(room.code)}`;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy this invite link:', link);
    }
  };

  // ---------------------------------------------------------------------------

  const shell = (children: React.ReactNode) => (
    <main
      className="min-h-screen text-[#3d2716] flex flex-col items-center justify-center p-4 sm:p-8 font-serif relative bg-cover bg-center bg-no-repeat bg-fixed"
      style={{ backgroundImage: "url('/background.avif')" }}
    >
      <div className="absolute inset-0 bg-[#f5ede0]/80 backdrop-blur-[1px] pointer-events-none" />
      <section className={card}>{children}</section>
    </main>
  );

  if (token === null || fatal) {
    return shell(
      <div className="text-center space-y-5 max-w-md mx-auto">
        <div className="text-5xl" aria-hidden="true">🏰 🔒</div>
        <h1 className="text-2xl font-bold text-[#3a2211]">You&apos;re not in this party yet</h1>
        <p className="text-[#634931] italic">{fatal || 'Join with the room code from whoever invited you.'}</p>
        <Link href="/group" className={`${primaryBtn} block text-center`}>Create or join a party →</Link>
      </div>
    );
  }

  if (!room) return shell(<p className="text-center italic text-[#634931] py-10">Puss is finding your party...</p>);

  const host = room.members.find((m) => m.is_host);
  const finished = room.members.filter((m) => m.done).length;
  const waitingOn = room.members.filter((m) => !m.done).map((m) => m.name);
  const notVoted = room.members.filter((m) => !m.voted).map((m) => m.name);

  const header = (
    <div className="flex items-center justify-between text-xs font-sans border-b border-[#ddcbb2] pb-3 mb-6">
      <Link href="/group" className="text-[#8b4f26] hover:underline">← Leave</Link>
      <span className="uppercase tracking-[0.2em] text-[#936d3f] font-bold">Party {room.code} · {room.city.split(',')[0]}</span>
    </div>
  );

  const roster = (show: 'joined' | 'answers' | 'votes') => (
    <ul className="space-y-1.5 font-sans text-sm">
      {room.members.map((m) => {
        const status =
          show === 'answers' ? (m.done ? '✓ ready' : `${m.answered}/${room.questions_per_member}`)
          : show === 'votes' ? (m.voted ? '✓ voted' : 'deciding…')
          : '';
        return (
          <li key={m.id} className="flex items-center justify-between bg-[#faf4e8] border border-[#e2d2bb] rounded-lg px-3 py-2">
            <span className="text-[#3c2817]">
              {m.is_host ? '👑 ' : '🐾 '}{m.name}{m.id === room.me.id ? ' (you)' : ''}
            </span>
            {status && <span className={`text-xs ${status.startsWith('✓') ? 'text-[#2e6b4d] font-bold' : 'text-[#a68c71]'}`}>{status}</span>}
          </li>
        );
      })}
    </ul>
  );

  const actionError = actionErrorAt && actionErrorAt.status === room.status ? actionErrorAt.message : '';
  const errorLine = (actionError || room.message) && (
    <p role="alert" className="text-sm text-[#a3331f] font-sans text-center">{actionError || room.message}</p>
  );

  // LOBBY ---------------------------------------------------------------------
  if (room.status === 'lobby') {
    return shell(
      <div className="max-w-md mx-auto space-y-6">
        {header}
        <div className="text-center space-y-2">
          <div className="text-xs uppercase tracking-[0.25em] text-[#936d3f] font-sans font-bold">The party gathers</div>
          <p className="text-[#634931] italic">Share this code so friends can join:</p>
          <div className="text-4xl font-extrabold tracking-[0.15em] text-[#3a2211] select-all" data-testid="room-code">{room.code}</div>
          <button onClick={copyInvite} className="text-sm font-sans text-[#8b4f26] underline cursor-pointer">
            {copied ? 'Invite link copied!' : 'Copy invite link'}
          </button>
        </div>
        <div>
          <h2 className="text-sm font-sans font-bold text-[#59391e] mb-2">Adventurers ({room.members.length})</h2>
          {roster('joined')}
        </div>
        {errorLine}
        {room.me.is_host ? (
          <div className="space-y-2">
            <button className={primaryBtn} disabled={busy} onClick={() => act('/start')}>
              Start the quest →
            </button>
            {room.members.length < 2 && (
              <p className="text-xs text-center italic text-[#a68c71] font-sans">Waiting for companions… (you can also start alone)</p>
            )}
          </div>
        ) : (
          <p className="text-center italic text-[#634931]">Waiting for {host?.name || 'the host'} to start the quest…</p>
        )}
      </div>
    );
  }

  // ANSWERING -----------------------------------------------------------------
  if (room.status === 'answering') {
    if (!room.me.done) {
      return shell(
        <div className="max-w-xl mx-auto space-y-5">
          {header}
          {question ? (
            <>
              <div className="flex items-center justify-between text-xs font-sans">
                <span className="text-[#966f3f] font-bold tracking-widest uppercase">
                  Your clue {question.number || room.me.answered + 1} of {room.questions_per_member}
                </span>
                <span className="text-[#a68c71]">{finished}/{room.members.length} ready</span>
              </div>
              <h2 className="text-xl sm:text-2xl font-bold text-[#351e0e] leading-snug">&ldquo;{question.question}&rdquo;</h2>
              <div className="space-y-2">
                {question.options.map((opt) => (
                  <button
                    key={opt}
                    disabled={busy}
                    onClick={() => answer(opt)}
                    className="w-full p-3.5 text-left text-sm bg-[#faf4e8] hover:bg-[#ebdcc7] rounded-xl border border-[#d6c1a5] transition cursor-pointer flex items-center justify-between shadow-sm disabled:opacity-50"
                  >
                    <span className="text-[#3c2817] font-medium">{opt}</span>
                    <span className="text-[#b58c56]">🐾</span>
                  </button>
                ))}
              </div>
              <form className="flex gap-2 font-sans" onSubmit={(e) => { e.preventDefault(); answer(custom); }}>
                <input
                  type="text"
                  value={custom}
                  maxLength={200}
                  onChange={(e) => setCustom(e.target.value)}
                  placeholder={question.placeholder || "Not listed? Be specific, e.g. 'quiet patio with tacos'"}
                  className="w-full p-3 bg-[#fdfaf5] border border-[#caa87d] rounded-xl text-sm focus:outline-none focus:border-[#8b4f26] text-[#3c2817] placeholder-[#b8a58f]"
                />
                <button disabled={busy || !custom.trim()} className="px-4 py-3 bg-[#8b4f26] hover:bg-[#733f1c] disabled:opacity-40 font-bold rounded-xl text-sm transition text-[#fcf8f0] cursor-pointer">↵</button>
              </form>
            </>
          ) : (
            <p className="text-center italic text-[#634931] py-8">Puss is preparing your question…</p>
          )}
          {errorLine}
        </div>
      );
    }
    return shell(
      <div className="max-w-md mx-auto space-y-6">
        {header}
        <div className="text-center space-y-2">
          <div className="text-5xl" aria-hidden="true">📜✓</div>
          <h2 className="text-2xl font-bold text-[#3a2211]">Your wishes are sealed</h2>
          <p className="text-[#634931] italic">
            {waitingOn.length ? `Waiting for ${waitingOn.join(', ')}…` : 'Everyone is ready!'}
          </p>
        </div>
        {roster('answers')}
        {errorLine}
        {room.me.is_host && (waitingOn.length > 0 || room.message) && (
          <button className={secondaryBtn} disabled={busy} onClick={() => act('/search')}>
            {waitingOn.length ? `Find our spot now (${finished}/${room.members.length} ready)` : 'Try the search again'}
          </button>
        )}
      </div>
    );
  }

  // SEARCHING -----------------------------------------------------------------
  if (room.status === 'searching') {
    return shell(
      <div className="max-w-md mx-auto py-10 text-center space-y-4">
        <div className="text-5xl animate-bounce" aria-hidden="true">🐾 🗺️</div>
        <h2 className="text-2xl font-bold text-[#59391e]">Puss is weighing everyone&apos;s wishes…</h2>
        <p className="text-sm italic text-[#8c6b47]">Scouting {room.city} for a spot the whole party will love.</p>
      </div>
    );
  }

  // VOTING / DONE -------------------------------------------------------------
  const basedOn = room.results[0]?.based_on || [];
  const leftOut = room.members.filter((m) => basedOn.length && !basedOn.includes(m.name)).map((m) => m.name);
  const basedOnLine = basedOn.length > 0 && (
    <p className="text-xs font-sans text-[#8c6b47]">
      Based on {basedOn.join(' & ')}&apos;s answers{leftOut.length ? ` (${leftOut.join(', ')} hadn't finished)` : ''}
    </p>
  );
  const done = room.status === 'done';
  const winner = done && room.winner !== null ? room.results[room.winner] : null;

  const placeCard = (r: RoomState['results'][number], i: number, big = false) => {
    const mine = room.me.vote === i;
    return (
      <div key={i} className={`rounded-2xl border ${mine ? 'border-[#8b4f26] ring-2 ring-[#8b4f26]/30' : 'border-[#cbaf8b]'} bg-[#faf4e8] overflow-hidden shadow-sm`}>
        {r.place.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element -- remote Google photo, same as the solo page
          <img src={r.place.thumbnail} alt={r.place.name || 'Place photo'} className={`w-full ${big ? 'h-52' : 'h-32'} object-cover`} />
        ) : (
          <div className={`w-full ${big ? 'h-24' : 'h-16'} bg-[#f3e7d3] flex items-center justify-center text-xs italic text-[#8c6b47]`}>🗺️ {room.city}</div>
        )}
        <div className="p-4 space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className={`${big ? 'text-2xl' : 'text-lg'} font-bold text-[#351e0e] leading-tight`}>{r.place.name}</h3>
              <p className="text-xs italic text-[#8c6b47]">
                {r.place.category}{r.place.rating ? ` · ${r.place.rating}★` : ''}
              </p>
            </div>
            <span className="shrink-0 text-xs font-sans font-bold bg-[#ede1ce] border border-[#cbb393] rounded-full px-2.5 py-1 text-[#6d4d29]">
              {r.votes} vote{r.votes === 1 ? '' : 's'}
            </span>
          </div>
          <p className="text-sm italic text-[#4d3522]">&ldquo;{r.reason}&rdquo;</p>
          {r.per_person && r.per_person.length > 0 && (
            <ul className="space-y-1 font-sans text-xs text-[#4d3522]">
              {r.per_person.map((p) => (
                <li key={p.name} className="flex gap-1.5">
                  <span aria-hidden="true">🐾</span>
                  <span><strong>{p.name}{p.name === room.me.name ? ' (you)' : ''}:</strong> {p.why}</span>
                </li>
              ))}
            </ul>
          )}
          {!done && (
            <button
              disabled={busy}
              onClick={() => act('/vote', { index: i })}
              className={mine ? `${primaryBtn} py-2.5` : `${secondaryBtn} py-2.5`}
            >
              {mine ? '✓ Your vote' : 'Vote for this'}
            </button>
          )}
          {big && (
            <a href={mapsLink(r.place, room.city)} target="_blank" rel="noreferrer"
               className="block w-full py-3.5 bg-gradient-to-r from-[#2e6b4d] to-[#25573e] hover:from-[#25573e] hover:to-[#1c432f] font-sans font-bold text-center text-sm rounded-xl text-emerald-50 border border-emerald-400/40">
              Set Forth Together →
            </a>
          )}
        </div>
      </div>
    );
  };

  if (done && winner) {
    return shell(
      <div className="max-w-lg mx-auto space-y-6">
        {header}
        <div className="text-center">
          <span className="text-xs uppercase tracking-[0.2em] text-[#936d3f] font-sans font-bold">👑 The party has chosen</span>
          <div className="mt-1">{basedOnLine}</div>
        </div>
        {placeCard(winner, room.winner as number, true)}
        {room.results.length > 1 && (
          <details className="font-sans text-sm text-[#59391e]">
            <summary className="cursor-pointer">The other contenders</summary>
            <ul className="mt-2 space-y-1">
              {room.results.map((r, i) => i !== room.winner && (
                <li key={i}>{r.place.name} — {r.votes} vote{r.votes === 1 ? '' : 's'}</li>
              ))}
            </ul>
          </details>
        )}
        <div className="grid grid-cols-2 gap-2">
          <Link href="/group" className={`${secondaryBtn} block text-center`}>New party</Link>
          <Link href="/" className={`${secondaryBtn} block text-center`}>Solo quest</Link>
        </div>
      </div>
    );
  }

  return shell(
    <div className="space-y-6">
      {header}
      <div className="text-center space-y-1">
        <div className="text-xs uppercase tracking-[0.25em] text-[#936d3f] font-sans font-bold">Cast your vote</div>
        <h2 className="text-2xl font-bold text-[#3a2211]">Puss found {room.results.length} spots for your party</h2>
        {basedOnLine}
        <p className="text-sm italic text-[#634931]">
          {notVoted.length ? `Still deciding: ${notVoted.join(', ')}` : 'Everyone has voted!'}
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">{room.results.map((r, i) => placeCard(r, i))}</div>
      {errorLine}
      {room.me.is_host && (
        <button className={secondaryBtn} disabled={busy || room.results.every((r) => r.votes === 0)} onClick={() => act('/reveal')}>
          Reveal the winner now
        </button>
      )}
    </div>
  );
}
