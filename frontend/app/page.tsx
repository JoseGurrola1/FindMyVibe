'use client';

import React, { useState } from 'react';

interface HistoryItem {
  question: string;
  answer: string;
}

interface Place {
  candidate_id?: string;
  place_id?: string;
  name?: string;
  title?: string;
  category?: string;
  rating?: number;
  reviews?: number;
  address?: string;
  thumbnail?: string;
}

export default function Home() {
  const [screen, setScreen] = useState<'START' | 'QUESTION' | 'GUESS' | 'REJECT'>('START');
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [rejectedIds, setRejectedIds] = useState<string[]>([]);
  const [rejectionFeedback, setRejectionFeedback] = useState<string[]>([]);

  const [currentQuestion, setCurrentQuestion] = useState<{ question: string; options?: string[] } | null>(null);
  const [currentGuess, setCurrentGuess] = useState<{ place?: Place; reason?: string } | null>(null);
  const [customInput, setCustomInput] = useState('');
  const [loading, setLoading] = useState(false);

  // Start-screen answers: where (required), what and when (optional).
  const [city, setCity] = useState('');
  const [what, setWhat] = useState('');
  const [when, setWhen] = useState('');
  // Short name for display, e.g. "Denver, CO" -> "Denver".
  const cityLabel = city.trim() ? city.trim().split(',')[0].trim() : 'Your City';

  // Returns true if the game moved forward, false if the request failed
  // (so callers only record an answer once the server accepted it).
  const advanceGame = async (
    newHistory: HistoryItem[],
    newRejectedIds: string[],
    newFeedback: string[]
  ): Promise<boolean> => {
    setLoading(true);
    try {
      // Relative URL: same site in production (Caddy routes /api to FastAPI);
      // in development, next.config.ts forwards /api to localhost:8000.
      const res = await fetch('/api/game/next', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          city: city.trim(),
          what: what.trim(),
          when: when.trim(),
          history: newHistory,
          rejected_ids: newRejectedIds,
          rejection_feedback: newFeedback,
        }),
      });

      if (res.status === 429) {
        // Rate limited: tell the player how long to wait; keep their place.
        const body = await res.json().catch(() => ({}));
        const wait = Number(body.retry_after || res.headers.get('Retry-After')) || 60;
        const when = wait >= 120 ? `${Math.ceil(wait / 60)} minutes` : `${wait} seconds`;
        alert(`Puss needs a catnap! Too many questions too fast. Try again in ${when}.`);
        return false;
      }

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();

      if (data.action === 'ask_question') {
        setCurrentQuestion({
          question: data.question,
          options: data.options || [],
        });
        setScreen('QUESTION');
      } else if (data.action === 'guess') {
        setCurrentGuess({
          place: data.place || data.candidate || data,
          reason: data.reason,
        });
        setScreen('GUESS');
      } else if (data.action === 'no_match') {
        alert(data.message || 'Puss found no enchanted places matching your words!');
        setScreen('START');
      }
      return true;
    } catch (err) {
      console.error('Tavern dispatch failed:', err);
      alert('Puss could not reach his tavern. Please try again in a moment.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const handleStart = () => {
    if (!city.trim() || loading) return;
    setHistory([]);
    setRejectedIds([]);
    setRejectionFeedback([]);
    advanceGame([], [], []);
  };

  const handleAnswer = async (answer: string) => {
    if (!currentQuestion || loading) return;
    const nextHistory = [...history, { question: currentQuestion.question, answer }];
    if (await advanceGame(nextHistory, rejectedIds, rejectionFeedback)) {
      setHistory(nextHistory);
      setCustomInput('');
    }
  };

  const handleReject = async (reason: string) => {
    const id = currentGuess?.place?.candidate_id || currentGuess?.place?.place_id || currentGuess?.place?.name || 'unknown_realm';
    const nextRejectedIds = [...rejectedIds, id];
    const nextFeedback = [...rejectionFeedback, reason];

    if (loading) return;
    if (await advanceGame(history, nextRejectedIds, nextFeedback)) {
      setRejectedIds(nextRejectedIds);
      setRejectionFeedback(nextFeedback);
    }
  };

  const placeName = currentGuess?.place?.name || currentGuess?.place?.title || 'An Enchanted Haven';

  return (
    <main
      className="min-h-screen text-[#3d2716] flex flex-col items-center justify-center p-4 sm:p-8 font-serif selection:bg-amber-300 selection:text-amber-950 relative overflow-hidden bg-cover bg-center bg-no-repeat bg-fixed"
      style={{ backgroundImage: "url('/background.avif')" }}
    >
      {/* Semi-transparent parchment tint overlay to ensure text stays readable */}
      <div className="absolute inset-0 bg-[#f5ede0]/80 backdrop-blur-[1px] pointer-events-none" />

      {/* Main Storybook Container */}
      <div className="relative z-10 w-full max-w-3xl bg-[#fcf8f0]/95 border-2 border-[#bfa27b] rounded-3xl p-6 sm:p-10 shadow-[0_15px_40px_rgba(120,70,30,0.2)] ring-1 ring-amber-900/10 backdrop-blur-sm">
      
        {/* Ornate Corner Accents */}
        <div className="absolute top-3.5 left-4 text-[#a88252] text-sm">✦</div>
        <div className="absolute top-3.5 right-4 text-[#a88252] text-sm">✦</div>
        <div className="absolute bottom-3.5 left-4 text-[#a88252] text-sm">✦</div>
        <div className="absolute bottom-3.5 right-4 text-[#a88252] text-sm">✦</div>

        {/* LOADING: PUSS IS SCOUTING */}
        {loading && (
          <div className="py-16 text-center space-y-4">
            <div className="text-5xl animate-bounce tracking-widest">🐾 🗡️</div>
            <h2 className="text-2xl font-bold tracking-wide text-[#59391e]">Puss is exploring the realm...</h2>
            <p className="text-sm text-[#8c6b47] italic max-w-sm mx-auto">
              Deciphering dusty tavern scrolls and scouting the streets of {cityLabel}...
            </p>
          </div>
        )}

        {/* START SCREEN: PROLOGUE */}
        {!loading && screen === 'START' && (
          <div className="text-center space-y-6 max-w-md mx-auto">
            <div className="inline-block p-4 rounded-full bg-[#f3e7d3] border-2 border-[#caa87d] shadow-sm">
              <span className="text-5xl">🏰 👢</span>
            </div>
            
            <div className="space-y-1">
              <span className="text-xs uppercase tracking-[0.25em] text-[#936d3f] font-sans font-bold">The Chronicles of {cityLabel}</span>
              <h1 className="text-3xl sm:text-4xl font-extrabold text-[#3a2211] tracking-wide">Find My Vibe</h1>
              <div className="w-20 h-0.5 bg-gradient-to-r from-transparent via-[#b58c56] to-transparent mx-auto mt-2" />
            </div>

            <p className="text-[#634931] text-base leading-relaxed italic">
              &ldquo;Halt, noble traveler! Tell me what atmosphere your heart longs for tonight, and I, Puss in Boots, shall guide your path to glory!&rdquo;
            </p>

            {/* Where / What / When */}
            <form
              className="space-y-3 text-left font-sans"
              onSubmit={(e) => { e.preventDefault(); handleStart(); }}
            >
              {[
                { id: 'where', label: 'Where?', hint: 'Required', value: city, set: setCity, placeholder: 'e.g. Austin, TX', max: 80 },
                { id: 'what', label: 'What?', hint: 'Optional', value: what, set: setWhat, placeholder: 'e.g. tacos, live music, a quiet bookstore', max: 120 },
                { id: 'when', label: 'When?', hint: 'Optional', value: when, set: setWhen, placeholder: 'e.g. tonight after 8pm, Saturday brunch', max: 120 },
              ].map((f) => (
                <label key={f.id} htmlFor={f.id} className="block">
                  <span className="flex items-baseline justify-between mb-1">
                    <span className="text-xs font-bold uppercase tracking-[0.2em] text-[#8b4f26]">{f.label}</span>
                    <span className="text-[11px] text-[#a68c71] italic">{f.hint}</span>
                  </span>
                  <input
                    id={f.id}
                    type="text"
                    value={f.value}
                    maxLength={f.max}
                    placeholder={f.placeholder}
                    onChange={(e) => f.set(e.target.value)}
                    autoComplete="off"
                    className="w-full p-3 bg-[#fdfaf5] border border-[#caa87d] rounded-xl text-sm focus:outline-none focus:border-[#8b4f26] text-[#3c2817] placeholder-[#b8a58f]"
                  />
                </label>
              ))}
              <button type="submit" hidden aria-hidden="true" tabIndex={-1} />
            </form>

            <button
              onClick={handleStart}
              disabled={!city.trim()}
              className="w-full py-4 disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-[#8b4f26] via-[#a35e2e] to-[#8b4f26] hover:from-[#75411d] hover:to-[#75411d] font-sans font-bold text-sm tracking-wider uppercase rounded-xl transition duration-200 shadow-lg shadow-amber-900/20 active:scale-[0.98] text-[#fcf8f0] border border-[#d4a86a] cursor-pointer"
            >
              Embark on the Quest →
            </button>
          </div>
        )}

        {/* QUESTION SCREEN: PUSS ASKS THE CLUES */}
        {!loading && screen === 'QUESTION' && currentQuestion && (
          <div className="flex flex-col md:flex-row gap-6 items-center">
            
            {/* PUSS IN BOOTS COMPANION CARD */}
            <div className="w-full md:w-5/12 flex flex-col items-center text-center p-4 bg-[#f3e7d3]/80 border border-[#cbaf8b] rounded-2xl shadow-inner">
              <div className="w-32 h-32 sm:w-36 sm:h-36 rounded-full overflow-hidden border-2 border-[#b58c56] bg-[#eadecc] flex items-center justify-center shadow-md mb-3">
                {/* 
                  Drop your image into frontend/public/puss.png to display it here.
                  If the file doesn't exist yet, it displays the fallback icon cleanly.
                */}
                <img
                  src="/puss.png"
                  alt="Puss in Boots"
                  className="w-full h-full object-cover object-top"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                    if (e.currentTarget.nextElementSibling) {
                      (e.currentTarget.nextElementSibling as HTMLElement).style.display = 'flex';
                    }
                  }}
                />
                <div style={{ display: 'none' }} className="w-full h-full items-center justify-center text-5xl">
                  😼👢
                </div>
              </div>
              <h3 className="font-bold text-base text-[#3a2211]">Puss in Boots</h3>
              <p className="text-xs text-[#8c6b47] italic mt-0.5">Your Swashbuckling Guide</p>
            </div>

            {/* DIALOGUE & QUESTIONS */}
            <div className="w-full md:w-7/12 space-y-5">
              <div className="flex items-center justify-between text-xs border-b border-[#ddcbb2] pb-2 font-sans">
                <span className="text-[#966f3f] font-bold tracking-widest uppercase">
                  Clue #{history.length + 1}
                </span>
                <span className="bg-[#ede1ce] border border-[#cbb393] px-2.5 py-0.5 rounded-full text-[#6d4d29] text-[11px]">
                  ⚔️ Puss Inquires
                </span>
              </div>

              <h2 className="text-xl sm:text-2xl font-bold text-[#351e0e] leading-snug">
                &ldquo;{currentQuestion.question}&rdquo;
              </h2>

              <div className="space-y-2">
                {currentQuestion.options && currentQuestion.options.length > 0 ? (
                  currentQuestion.options.map((opt, i) => (
                    <button
                      key={i}
                      onClick={() => handleAnswer(opt)}
                      className="w-full p-3.5 text-left text-sm bg-[#faf4e8] hover:bg-[#ebdcc7] hover:border-[#a88252] rounded-xl border border-[#d6c1a5] transition duration-200 cursor-pointer flex items-center justify-between group shadow-sm"
                    >
                      <span className="text-[#3c2817] font-medium group-hover:text-[#211409]">{opt}</span>
                      <span className="text-[#b58c56] group-hover:translate-x-1 transition duration-200">🐾</span>
                    </button>
                  ))
                ) : null}
              </div>

              {/* Custom Answer Input */}
              <div className="pt-1">
                <div className="flex gap-2 font-sans">
                  <input
                    type="text"
                    placeholder="Whisper a custom answer..."
                    value={customInput}
                    onChange={(e) => setCustomInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && customInput.trim() && handleAnswer(customInput.trim())}
                    className="w-full p-3 bg-[#fdfaf5] border border-[#caa87d] rounded-xl text-sm focus:outline-none focus:border-[#8b4f26] text-[#3c2817] placeholder-[#a68c71]"
                  />
                  <button
                    onClick={() => customInput.trim() && handleAnswer(customInput.trim())}
                    disabled={!customInput.trim()}
                    className="px-4 py-3 bg-[#8b4f26] hover:bg-[#733f1c] disabled:opacity-40 font-bold rounded-xl text-sm transition text-[#fcf8f0] cursor-pointer"
                  >
                    ↵
                  </button>
                </div>
              </div>
            </div>

          </div>
        )}

        {/* GUESS CARD: THE REVELATION */}
        {!loading && screen === 'GUESS' && currentGuess && (
          <div className="space-y-6 max-w-lg mx-auto">
            <div className="text-center">
              <span className="text-xs uppercase tracking-[0.2em] text-[#936d3f] font-sans font-bold">
                👑 The Destination Revealed
              </span>
              <h2 className="text-2xl sm:text-3xl font-extrabold mt-1 text-[#351e0e]">{placeName}</h2>
              <p className="text-xs text-[#8c6b47] mt-0.5 italic">{currentGuess.place?.category || `${cityLabel} Realm`}</p>
            </div>

            {currentGuess.place?.thumbnail ? (
              <img
                src={currentGuess.place.thumbnail}
                alt={placeName}
                className="w-full h-48 object-cover rounded-2xl border-2 border-[#cbaf8b] shadow-md"
              />
            ) : (
              <div className="w-full h-24 bg-[#f3e7d3] border border-[#cbaf8b] rounded-2xl flex items-center justify-center text-[#8c6b47] text-xs italic">
                🗺️ Charted within the boundaries of {city.trim()}
              </div>
            )}

            {/* Scroll Note */}
            <div className="p-4 bg-[#f3e7d3]/90 border-l-4 border-[#8b4f26] rounded-r-xl shadow-sm text-sm text-[#4d3522] leading-relaxed">
              <span className="font-sans font-bold text-[#8b4f26] block text-xs uppercase tracking-wider mb-1">
                😼 Puss&apos;s Proclamation:
              </span>
              <p className="italic">&ldquo;{currentGuess.reason || 'A true haven matched to the desires you spoke of.'}&rdquo;</p>
            </div>

            <div className="space-y-2.5 pt-1 font-sans">
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(placeName + ' ' + (currentGuess.place?.address || city.trim()))}`}
                target="_blank"
                rel="noreferrer"
                className="block w-full py-3.5 bg-gradient-to-r from-[#2e6b4d] to-[#25573e] hover:from-[#25573e] hover:to-[#1c432f] font-bold text-center text-sm rounded-xl transition shadow-md text-emerald-50 border border-emerald-400/40 cursor-pointer"
              >
                Set Forth to the Haven →
              </a>

              <button
                onClick={() => setScreen('REJECT')}
                className="w-full py-3 bg-[#ede1ce] hover:bg-[#e2d2ba] text-[#59391e] hover:text-[#351e0e] text-xs tracking-wider uppercase font-semibold rounded-xl border border-[#cbaf8b] transition cursor-pointer"
              >
                ⚔️ Nay, Send Puss Back to the Streets
              </button>
            </div>
          </div>
        )}

        {/* REJECT SCREEN: THE GRIEVANCE */}
        {!loading && screen === 'REJECT' && (
          <div className="space-y-5 max-w-lg mx-auto">
            <div>
              <span className="text-xs uppercase tracking-widest text-[#a84428] font-sans font-bold">
                A Displeasing Match
              </span>
              <h2 className="text-xl sm:text-2xl font-bold mt-1 text-[#351e0e]">What displeases you about {placeName}?</h2>
              <p className="text-xs text-[#7d5d3b] mt-1 italic">
                State your grievance so Puss can sharpen his instincts and sniff out a finer spot:
              </p>
            </div>

            <div className="space-y-2 font-sans">
              {[
                'Too crowded & noisy for my taste',
                'Far too costly for humble travelers',
                'The atmosphere feels uninspiring',
                'I yearn for a breezier outdoor garden',
                'I demand games, pastimes, and merriment'
              ].map((reason, i) => (
                <button
                  key={i}
                  onClick={() => handleReject(reason)}
                  className="w-full p-3.5 text-left text-xs sm:text-sm bg-[#faf4e8] hover:bg-[#ebdcc7] hover:border-[#a88252] rounded-xl border border-[#d6c1a5] text-[#3c2817] font-medium transition cursor-pointer flex items-center gap-2.5 shadow-sm"
                >
                  <span className="text-[#a84428]">🗡️</span>
                  <span>{reason}</span>
                </button>
              ))}
            </div>

            <div className="pt-2 font-sans">
              <input
                type="text"
                placeholder="Or decree what you desire instead..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.currentTarget.value.trim()) {
                    handleReject(e.currentTarget.value.trim());
                  }
                }}
                className="w-full p-3.5 bg-[#fdfaf5] border border-[#caa87d] rounded-xl text-xs sm:text-sm focus:outline-none focus:border-[#8b4f26] text-[#3c2817] placeholder-[#a68c71]"
              />
            </div>

            <button
              onClick={() => setScreen('GUESS')}
              className="w-full py-2 text-xs text-[#8c6b47] hover:text-[#59391e] font-sans transition text-center"
            >
              ← Return to previous haven
            </button>
          </div>
        )}

      </div>
    </main>
  );
}