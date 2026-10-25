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

  // Calls your partner's /api/game/next endpoint
  const advanceGame = async (
    newHistory: HistoryItem[],
    newRejectedIds: string[],
    newFeedback: string[]
  ) => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/game/next', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          city: 'Austin TX',
          history: newHistory,
          rejected_ids: newRejectedIds,
          rejection_feedback: newFeedback,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

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
        alert(data.message || 'No matching places found.');
        setScreen('START');
      }
    } catch (err) {
      console.error('Error contacting backend:', err);
      alert('Could not connect to backend. Make sure main.py is running on port 8000!');
    } finally {
      setLoading(false);
    }
  };

  const handleStart = () => {
    setHistory([]);
    setRejectedIds([]);
    setRejectionFeedback([]);
    advanceGame([], [], []);
  };

  const handleAnswer = (answer: string) => {
    if (!currentQuestion) return;
    const nextHistory = [...history, { question: currentQuestion.question, answer }];
    setHistory(nextHistory);
    setCustomInput('');
    advanceGame(nextHistory, rejectedIds, rejectionFeedback);
  };

  const handleReject = (reason: string) => {
    const id = currentGuess?.place?.candidate_id || currentGuess?.place?.place_id || currentGuess?.place?.name || 'unknown_id';
    const nextRejectedIds = [...rejectedIds, id];
    const nextFeedback = [...rejectionFeedback, reason];

    setRejectedIds(nextRejectedIds);
    setRejectionFeedback(nextFeedback);

    // This triggers main.py: required_answers = 3 + len(rejected)
    // and sends Gemini's adaptive follow-up question!
    advanceGame(history, nextRejectedIds, nextFeedback);
  };

  const placeName = currentGuess?.place?.name || currentGuess?.place?.title || 'Selected Spot';

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-2xl p-6 shadow-2xl">

        {/* LOADING */}
        {loading && (
          <div className="py-12 text-center space-y-3">
            <div className="text-3xl animate-spin">🔮</div>
            <p className="text-sm text-neutral-400">Gemini is thinking...</p>
          </div>
        )}

        {/* START */}
        {!loading && screen === 'START' && (
          <div className="text-center space-y-6">
            <div className="text-5xl">🔍</div>
            <h1 className="text-2xl font-bold tracking-tight">Find My Vibe</h1>
            <p className="text-neutral-400 text-sm leading-relaxed">
              Answer Gemini&apos;s questions to find your spot. If you reject a match, Gemini will ask adaptive follow-ups to dial it in.
            </p>
            <button
              onClick={handleStart}
              className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 font-semibold rounded-xl transition cursor-pointer shadow-lg shadow-violet-600/20 active:scale-[0.98]"
            >
              Start Game
            </button>
          </div>
        )}

        {/* QUESTION (Dynamic from Gemini) */}
        {!loading && screen === 'QUESTION' && currentQuestion && (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs text-neutral-400">
              <span>Question {history.length + 1}</span>
              <span className="bg-neutral-800 px-2.5 py-1 rounded-full text-violet-400 border border-neutral-700">Akinator Mode</span>
            </div>

            <h2 className="text-lg font-semibold text-neutral-100 leading-snug">
              {currentQuestion.question}
            </h2>

            <div className="space-y-2">
              {currentQuestion.options && currentQuestion.options.length > 0 ? (
                currentQuestion.options.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => handleAnswer(opt)}
                    className="w-full p-3.5 text-left text-sm bg-neutral-800 hover:bg-neutral-700/80 rounded-xl border border-neutral-700/50 transition cursor-pointer"
                  >
                    👉 {opt}
                  </button>
                ))
              ) : null}
            </div>

            <div className="pt-2 flex gap-2">
              <input
                type="text"
                placeholder="Or type your own answer..."
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && customInput.trim() && handleAnswer(customInput.trim())}
                className="w-full p-3 bg-neutral-800 border border-neutral-700 rounded-xl text-sm focus:outline-none focus:border-violet-500"
              />
              <button
                onClick={() => customInput.trim() && handleAnswer(customInput.trim())}
                disabled={!customInput.trim()}
                className="px-4 py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 font-semibold rounded-xl text-sm transition"
              >
                ↵
              </button>
            </div>
          </div>
        )}

        {/* GUESS */}
        {!loading && screen === 'GUESS' && currentGuess && (
          <div className="space-y-5">
            <div className="text-center">
              <span className="text-xs uppercase tracking-wider text-violet-400 font-semibold">Gemini&apos;s Match</span>
              <h2 className="text-xl font-bold mt-1">{placeName}</h2>
              <p className="text-xs text-neutral-400 mt-0.5">{currentGuess.place?.category || 'Austin Venue'}</p>
            </div>

            {currentGuess.place?.thumbnail ? (
              <img
                src={currentGuess.place.thumbnail}
                alt={placeName}
                className="w-full h-44 object-cover rounded-xl border border-neutral-800"
              />
            ) : (
              <div className="w-full h-24 bg-neutral-800/40 border border-neutral-700/40 rounded-xl flex items-center justify-center text-neutral-500 text-xs">
                📍 {placeName}
              </div>
            )}

            <div className="p-3 bg-violet-950/40 border border-violet-800/50 rounded-xl text-xs text-violet-200">
              💡 <strong>Why this fits:</strong> {currentGuess.reason || 'Selected based on your preferences.'}
            </div>

            <div className="space-y-2 pt-2">
              <a
                href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(placeName + ' ' + (currentGuess.place?.address || 'Austin TX'))}`}
                target="_blank"
                rel="noreferrer"
                className="block w-full py-3 bg-emerald-600 hover:bg-emerald-500 font-semibold text-center text-sm rounded-xl transition shadow-lg shadow-emerald-600/20"
              >
                Spot on! Let&apos;s Go →
              </a>

              <button
                onClick={() => setScreen('REJECT')}
                className="w-full py-2.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-sm font-medium rounded-xl transition cursor-pointer"
              >
                Not my vibe (Reject & refine)
              </button>
            </div>
          </div>
        )}

        {/* REJECT / FEEDBACK */}
        {!loading && screen === 'REJECT' && (
          <div className="space-y-4">
            <div>
              <span className="text-xs uppercase tracking-wider text-rose-400 font-semibold">Refine Search</span>
              <h2 className="text-lg font-bold mt-1">What was off about {placeName}?</h2>
              <p className="text-xs text-neutral-400 mt-1">Pick a reason or type your feedback below:</p>
            </div>

            <div className="space-y-2">
              {['Too crowded / loud', 'Too expensive', 'Wrong atmosphere', 'Looking for outdoor patio', 'Prefer activities / games'].map((reason, i) => (
                <button
                  key={i}
                  onClick={() => handleReject(reason)}
                  className="w-full p-3 text-left text-sm bg-neutral-800 hover:bg-neutral-700/80 rounded-xl border border-neutral-700/50 transition cursor-pointer"
                >
                  👎 {reason}
                </button>
              ))}
            </div>

            <div className="pt-2">
              <input
                type="text"
                placeholder="Or describe what you want instead..."
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.currentTarget.value.trim()) {
                    handleReject(e.currentTarget.value.trim());
                  }
                }}
                className="w-full p-3 bg-neutral-800 border border-neutral-700 rounded-xl text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
          </div>
        )}

      </div>
    </main>
  );
}