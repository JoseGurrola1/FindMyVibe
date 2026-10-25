import { Suspense } from 'react';
import GroupRoom from './GroupRoom';

// The room id comes from the URL at request time, so the client component
// that reads it must sit inside a Suspense boundary (cacheComponents is on).
export default function GroupRoomPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center bg-[#f5ede0] font-serif text-[#59391e]">
          Puss is finding your party...
        </main>
      }
    >
      <GroupRoom />
    </Suspense>
  );
}
