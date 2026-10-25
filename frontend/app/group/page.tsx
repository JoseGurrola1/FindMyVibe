'use client';

import { useState, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

type Mode = 'create' | 'join';

const noSubscribe = () => () => {};
// Invite links look like /group?code=VIBE-4K2P.
const invitedCode = () => new URLSearchParams(window.location.search).get('code');

/**
 * Group Mode entry screen (backend: group_routes.py).
 * POST /api/groups {name, city} -> {room_id, code, member_token}
 * POST /api/groups/join {code, name} -> {room_id, code, member_token}
 * The member token is sent as X-Member-Token on every room request.
 */
export default function GroupPage() {
  const router = useRouter();
  const invited = useSyncExternalStore(noSubscribe, invitedCode, () => null);
  const [chosenMode, setMode] = useState<Mode | null>(null);
  const [name, setName] = useState('');
  const [city, setCity] = useState('Austin, TX');
  const [typedCode, setCode] = useState<string | null>(null);
  // With an invite link, open on "Join" with the code filled in.
  const mode: Mode = chosenMode ?? (invited ? 'join' : 'create');
  const code = typedCode ?? (invited ? invited.toUpperCase() : '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim() || busy) return;
    if (mode === 'create' && !city.trim()) return;
    if (mode === 'join' && !code.trim()) return;

    setError('');
    setBusy(true);
    try {
      const path = mode === 'create' ? '/api/groups' : '/api/groups/join';
      const payload = mode === 'create'
        ? { name: name.trim(), city: city.trim() }
        : { name: name.trim(), code: code.trim().toUpperCase() };
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || data.message || `Request failed (${res.status})`);
      if (!data.room_id || !data.member_token) throw new Error('The group server returned an incomplete room session.');

      // A private token scoped to this room and browser tab. Server must validate it on every write.
      sessionStorage.setItem(`findmyvibe:member:${data.room_id}`, data.member_token);
      router.push(`/group/${encodeURIComponent(data.room_id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not contact the group server.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <main
      className="min-h-screen text-[#3d2716] flex flex-col items-center justify-center p-4 sm:p-8 font-serif bg-cover bg-center bg-no-repeat bg-fixed relative"
      style={{ backgroundImage: "url('/background.avif')" }}
    >
      <div className="absolute inset-0 bg-[#f5ede0]/80 backdrop-blur-[1px] pointer-events-none" />
      <section className="relative z-10 w-full max-w-xl bg-[#fcf8f0]/95 border-2 border-[#bfa27b] rounded-3xl p-6 sm:p-10 shadow-[0_15px_40px_rgba(120,70,30,0.2)]">
        <Link href="/" className="text-sm font-sans text-[#8b4f26] hover:underline">← Return to the solo quest</Link>
        <div className="text-center space-y-3 mt-7 mb-7">
          <div className="text-5xl" aria-hidden="true">🏰 👥</div>
          <div className="text-xs uppercase tracking-[0.25em] text-[#936d3f] font-sans font-bold">A fellowship of adventurers</div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-[#3a2211]">Find Our Vibe</h1>
          <p className="text-[#634931] italic">Each traveler shares their wishes. Puss finds an adventure for everyone.</p>
        </div>

        <div className="grid grid-cols-2 gap-2 mb-6 font-sans">
          <button type="button" onClick={() => { setMode('create'); setError(''); }} aria-pressed={mode === 'create'} className={`rounded-xl border px-3 py-3 font-bold text-sm ${mode === 'create' ? 'bg-[#8b4f26] text-white border-[#8b4f26]' : 'bg-[#f3e7d3] text-[#59391e] border-[#cbaf8b]'}`}>Create a party</button>
          <button type="button" onClick={() => { setMode('join'); setError(''); }} aria-pressed={mode === 'join'} className={`rounded-xl border px-3 py-3 font-bold text-sm ${mode === 'join' ? 'bg-[#8b4f26] text-white border-[#8b4f26]' : 'bg-[#f3e7d3] text-[#59391e] border-[#cbaf8b]'}`}>Join a party</button>
        </div>

        <form onSubmit={submit} className="space-y-4 font-sans">
          <label className="block text-sm font-semibold text-[#59391e]">
            Your name
            <input required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} placeholder="What shall Puss call you?" className="mt-1 w-full p-3 rounded-xl border border-[#caa87d] bg-[#fdfaf5] focus:outline-none focus:border-[#8b4f26]" />
          </label>
          {mode === 'create' ? (
            <label className="block text-sm font-semibold text-[#59391e]">
              City
              <input required value={city} onChange={(e) => setCity(e.target.value)} placeholder="Austin, TX" className="mt-1 w-full p-3 rounded-xl border border-[#caa87d] bg-[#fdfaf5] focus:outline-none focus:border-[#8b4f26]" />
            </label>
          ) : (
            <label className="block text-sm font-semibold text-[#59391e]">
              Room code
              <input required autoCapitalize="characters" value={code} onChange={(e) => setCode(e.target.value)} placeholder="VIBE-4K2P" className="mt-1 w-full p-3 rounded-xl border border-[#caa87d] bg-[#fdfaf5] focus:outline-none focus:border-[#8b4f26] uppercase" />
            </label>
          )}
          {error && <p role="alert" className="text-sm text-[#a3331f]">{error}</p>}
          <button disabled={busy || !name.trim() || (mode === 'create' ? !city.trim() : !code.trim())} className="w-full py-4 rounded-xl bg-gradient-to-r from-[#8b4f26] via-[#a35e2e] to-[#8b4f26] text-[#fcf8f0] font-bold tracking-wider uppercase text-sm disabled:opacity-50">
            {busy ? 'Summoning the party...' : mode === 'create' ? 'Create our quest →' : 'Join the quest →'}
          </button>
        </form>
        <p className="text-xs text-center text-[#8c6b47] mt-5 italic">Everyone answers a few questions on their own phone, then the party votes on Puss&apos;s top 3 picks.</p>
      </section>
    </main>
  );
}
