# FindMyVibe frontend

The Next.js app for FindMyVibe. Setup, running both servers, tests and
deployment are all in the [main README](../README.md).

Quick start (with the backend already running on port 8000):

```bash
npm ci
npm run dev
```

Then open http://localhost:3000. `/api` calls are forwarded to the backend by
`next.config.ts`.

- `app/page.tsx`: solo game
- `app/group/`: group mode (create/join, then the party room)
- `app/components/WalkingCat.tsx`: the cat mascot

This project uses a recent Next.js with breaking changes from older versions;
see `AGENTS.md` before changing framework-level code.
