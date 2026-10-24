'use client';

import React, { useState, useEffect } from 'react';

interface Place {
  title?: string;
  name?: string;
  category?: string;
  rating?: number;
  reviews?: number;
  price?: string;
  address?: string;
  thumbnail?: string;
  link?: string;
  description?: string;
}

const FALLBACK_PLACES: Place[] = [
  {
    name: "Cosmic Coffee + Beer Garden",
    category: "Coffee shop & Beer garden",
    rating: 4.7,
    reviews: 3200,
    address: "121 Pickle Rd, Austin, TX 78704",
    thumbnail: "https://images.unsplash.com/photo-1554118811-1e0d58224f24?auto=format&fit=crop&w=600&q=80",
    link: "https://maps.google.com/?q=Cosmic+Coffee+Beer+Garden+Austin",
    description: "Spacious outdoor garden with local beer, coffee, food trucks, and cozy night lighting."
  },
  {
    name: "The Long Goodbye",
    category: "Cocktail Bar & Coffee",
    rating: 4.6,
    reviews: 215,
    address: "2808 Manor Rd, Austin, TX 78722",
    thumbnail: "https://images.unsplash.com/photo-1514933651103-005eec06c04b?auto=format&fit=crop&w=600&q=80",
    link: "https://maps.google.com/?q=The+Long+Goodbye+Austin",
    description: "Chic retro 70s lounge with artisan cocktails, coffee, and a relaxed back patio."
  },
  {
    name: "Texas Toy Museum and Arcade",
    category: "Arcade & Museum",
    rating: 4.8,
    reviews: 1854,
    address: "312 Congress Ave., Austin, TX 78701",
    thumbnail: "https://images.unsplash.com/photo-1511512578047-dfb367046420?auto=format&fit=crop&w=600&q=80",
    link: "https://maps.google.com/?q=Texas+Toy+Museum+Austin",
    description: "Vintage arcade games, retro collectibles, craft beer, and casual fun."
  },
  {
    name: "Mozart's Coffee Roasters",
    category: "Bakery & Waterfront Cafe",
    rating: 4.5,
    reviews: 7400,
    address: "3825 Lake Austin Blvd, Austin, TX 78703",
    thumbnail: "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?auto=format&fit=crop&w=600&q=80",
    link: "https://maps.google.com/?q=Mozarts+Coffee+Roasters+Austin",
    description: "Scenic lakeside deck with live music, artisan coffee roasts, and European pastries."
  }
];

const QUESTIONS = [
  {
    id: 1,
    prompt: "What kind of energy or vibe are you looking for right now?",
    placeholder: "e.g., chill low-key patio, retro arcade, cozy speakeasy...",
    suggestions: ["Chill outdoor patio", "Quiet & cozy booth", "Upbeat & social"]
  },
  {
    id: 2,
    prompt: "What are you looking to do, eat, or drink?",
    placeholder: "e.g., craft cocktails, matcha latte, vintage games, dessert...",
    suggestions: ["Unique cocktails", "Coffee & pastries", "Casual snacks & drinks"]
  },
  {
    id: 3,
    prompt: "Any specific atmosphere, music, or scene preferences?",
    placeholder: "e.g., 70s aesthetics, dim lights, dog-friendly, lake view...",
    suggestions: ["Dim lights & intimate", "Dog-friendly patio", "Waterfront view"]
  }
];

export default function Home() {
  const [screen, setScreen] = useState<'START' | 'QUESTION' | 'GUESS'>('START');
  const [currentQIndex, setCurrentQIndex] = useState(0);
  const [inputText, setInputText] = useState('');
  const [userAnswers, setUserAnswers] = useState<string[]>([]);
  const [places, setPlaces] = useState<Place[]>(FALLBACK_PLACES);
  const [rankedMatches, setRankedMatches] = useState<Place[]>([]);
  const [guessIndex, setGuessIndex] = useState(0);

  useEffect(() => {
    fetch('/places.json')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        const results = data.local_results || data.places || (Array.isArray(data) ? data : []);
        if (results.length > 0) {
          setPlaces(results);
        }
      })
      .catch((err) => console.warn("Using fallback candidate list:", err));
  }, []);

  const rankPlacesByVibe = (answers: string[]) => {
    const rawTokens = answers
      .join(' ')
      .toLowerCase()
      .replace(/[^a-z0-9 ]/g, '')
      .split(/\s+/)
      .filter((word) => word.length > 2);

    const scored = places.map((place) => {
      let score = 0;
      const placeName = place.name || place.title || '';
      const searchableText = `${placeName} ${place.category || ''} ${place.description || ''} ${place.address || ''}`.toLowerCase();

      rawTokens.forEach((token) => {
        if (searchableText.includes(token)) score += 3;
      });

      if (place.rating && place.rating >= 4.5) score += 1;

      return { place, score };
    });

    scored.sort((a, b) => b.score - a.score);
    return scored.map((item) => item.place);
  };

  const handleStart = () => {
    setScreen('QUESTION');
    setCurrentQIndex(0);
    setUserAnswers([]);
    setInputText('');
    setGuessIndex(0);
  };

  const handleNextQuestion = async (answerToSubmit?: string) => {
    const finalAnswer = (answerToSubmit ?? inputText).trim();
    if (!finalAnswer) return;

    const nextAnswers = [...userAnswers, finalAnswer];
    setUserAnswers(nextAnswers);
    setInputText('');

    if (currentQIndex + 1 < QUESTIONS.length) {
      setCurrentQIndex(currentQIndex + 1);
    } else {
      // Query the live Python/SerpApi backend
      try {
        const res = await fetch('http://localhost:8000/api/find-vibe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: nextAnswers }),
        });
        const data = await res.json();
        if (data.places && data.places.length > 0) {
          setRankedMatches(data.places);
        } else {
          setRankedMatches(rankPlacesByVibe(nextAnswers));
        }
      } catch (err) {
        console.warn('API error, using local fallback:', err);
        setRankedMatches(rankPlacesByVibe(nextAnswers));
      }
      setGuessIndex(0);
      setScreen('GUESS');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleNextQuestion();
    }
  };

  const handleReject = () => {
    if (guessIndex + 1 < rankedMatches.length) {
      setGuessIndex(guessIndex + 1);
    } else {
      setGuessIndex(0);
    }
  };

  const currentMatch = rankedMatches[guessIndex] || places[0] || FALLBACK_PLACES[0];
  const currentQ = QUESTIONS[currentQIndex];
  const displayName = currentMatch.name || currentMatch.title || "Selected Spot";

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md bg-neutral-900 border border-neutral-800 rounded-2xl p-6 shadow-2xl">
        
        {/* START SCREEN */}
        {screen === 'START' && (
          <div className="text-center space-y-6">
            <div className="text-5xl">🔍</div>
            <h1 className="text-2xl font-bold tracking-tight">Find My Vibe</h1>
            <p className="text-neutral-400 text-sm leading-relaxed">
              Describe what you want in your own words. I&apos;ll read between the lines and guess your ideal destination.
            </p>
            <div className="bg-neutral-800/60 rounded-xl p-3.5 text-left border border-neutral-700/50">
              <label className="text-xs text-neutral-400 block mb-1">Target Area</label>
              <div className="text-sm font-semibold text-neutral-200">Austin, TX</div>
            </div>
            <button
              onClick={handleStart}
              className="w-full py-3.5 bg-violet-600 hover:bg-violet-500 font-semibold rounded-xl transition cursor-pointer shadow-lg shadow-violet-600/20 active:scale-[0.98]"
            >
              Start Finding My Vibe
            </button>
          </div>
        )}

        {/* QUESTION SCREEN */}
        {screen === 'QUESTION' && currentQ && (
          <div className="space-y-6">
            <div className="flex items-center justify-between text-xs text-neutral-400">
              <span>Question {currentQIndex + 1} of {QUESTIONS.length}</span>
              <span className="bg-neutral-800 px-2.5 py-1 rounded-full text-violet-400 border border-neutral-700">Akinator Mode</span>
            </div>

            <h2 className="text-lg font-semibold text-neutral-100 leading-snug">
              {currentQ.prompt}
            </h2>

            <div className="space-y-3">
              <div className="relative">
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={currentQ.placeholder}
                  autoFocus
                  className="w-full p-4 pr-12 bg-neutral-800/90 border border-neutral-700 rounded-xl text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition"
                />
                <button
                  type="button"
                  onClick={() => handleNextQuestion()}
                  disabled={!inputText.trim()}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 p-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:hover:bg-violet-600 text-white rounded-lg transition text-xs font-semibold cursor-pointer"
                >
                  ↵
                </button>
              </div>

              <div className="space-y-1.5 pt-1">
                <span className="text-[11px] text-neutral-500 uppercase tracking-wider font-medium">Quick ideas:</span>
                <div className="flex flex-wrap gap-1.5">
                  {currentQ.suggestions.map((suggestion, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleNextQuestion(suggestion)}
                      className="text-xs px-2.5 py-1.5 bg-neutral-800 hover:bg-neutral-700/80 text-neutral-300 rounded-lg border border-neutral-700/50 transition cursor-pointer"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={() => handleNextQuestion()}
              disabled={!inputText.trim()}
              className="w-full py-3 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:hover:bg-violet-600 font-semibold text-sm rounded-xl transition cursor-pointer shadow-lg shadow-violet-600/20 active:scale-[0.98]"
            >
              Next Step →
            </button>
          </div>
        )}

        {/* GUESS CARD */}
        {screen === 'GUESS' && currentMatch && (
          <div className="space-y-5">
            <div className="text-center">
              <span className="text-xs uppercase tracking-wider text-violet-400 font-semibold">My Match</span>
              <h2 className="text-xl font-bold mt-1">{displayName}</h2>
              <p className="text-xs text-neutral-400 mt-0.5">{currentMatch.category || 'Hangout Spot'}</p>
            </div>

            {currentMatch.thumbnail ? (
              <img
                src={currentMatch.thumbnail}
                alt={displayName}
                className="w-full h-44 object-cover rounded-xl border border-neutral-800"
              />
            ) : (
              <div className="w-full h-28 bg-neutral-800/40 border border-neutral-700/40 rounded-xl flex items-center justify-center text-neutral-500 text-xs">
                📍 {displayName}
              </div>
            )}

            <div className="bg-neutral-800/50 p-3.5 rounded-xl space-y-1.5 text-xs text-neutral-300 border border-neutral-700/40">
              <div className="flex justify-between">
                <span>Rating</span>
                <span className="font-semibold text-neutral-100">
                  ★ {currentMatch.rating ?? '4.6'} ({currentMatch.reviews ?? '100+'} reviews)
                </span>
              </div>
              <div className="flex justify-between">
                <span>Address</span>
                <span className="truncate max-w-[200px] text-neutral-400">{currentMatch.address || 'Austin, TX'}</span>
              </div>
            </div>

            <div className="p-3 bg-violet-950/40 border border-violet-800/50 rounded-xl text-xs text-violet-200">
              💡 <strong>Why this fits:</strong> Matches your picks: &ldquo;{userAnswers.filter(Boolean).join(' • ')}&rdquo;.
            </div>

            <div className="space-y-2 pt-2">
              <a
                href={currentMatch.link || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(displayName + ' ' + (currentMatch.address || 'Austin'))}`}
                target="_blank"
                rel="noreferrer"
                className="block w-full py-3 bg-emerald-600 hover:bg-emerald-500 font-semibold text-center text-sm rounded-xl transition shadow-lg shadow-emerald-600/20 active:scale-[0.98]"
              >
                Spot on! Let&apos;s Go →
              </a>

              <button
                onClick={handleReject}
                className="w-full py-2.5 bg-neutral-800 hover:bg-neutral-700 text-neutral-300 text-sm font-medium rounded-xl transition cursor-pointer active:scale-[0.98]"
              >
                Not my vibe (Show 2nd Guess)
              </button>
            </div>
          </div>
        )}

      </div>
    </main>
  );
}