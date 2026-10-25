"""
Group Mode API (registered in main.py).

    POST /api/groups                    {name, city}      -> create a party (you're the host)
    POST /api/groups/join               {code, name}      -> join with the room code
    GET  /api/groups/{room_id}                            -> room state (polled every ~2s)
    POST /api/groups/{room_id}/start                      -> host: start the questions
    POST /api/groups/{room_id}/turn     {question?, answer?} -> answer, get your next question
    POST /api/groups/{room_id}/search                     -> host: find places now (don't wait)
    POST /api/groups/{room_id}/vote     {index}           -> vote for one of the places
    POST /api/groups/{room_id}/reveal                     -> host: reveal the winner now

Every room call needs the X-Member-Token header from create/join.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gemini_ai import ask_question, choose_group_places, create_group_search_query
from groups import GroupError, GroupStore
from hours import annotate

log = logging.getLogger("findmyvibe.groups")

BROAD_QUERY = "things to do"


class CreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    city: str = Field(min_length=1, max_length=80)
    tz: str = Field("", max_length=64)  # host's browser time zone, for opening hours


class JoinRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=40)


class TurnRequest(BaseModel):
    question: str = Field("", max_length=300)
    answer: str = Field("", max_length=200)


class VoteRequest(BaseModel):
    index: int


def _error(e: GroupError):
    return JSONResponse(status_code=e.status, content={"detail": e.message})


def build_router(find_places, store=None):
    """
    `find_places(query, city)` is main.py's search (SerpApi with fallbacks),
    passed in to avoid a circular import.
    """
    store = store or GroupStore()
    router = APIRouter(prefix="/api/groups")
    router.store = store

    def run_search(room_id, job):
        """Find places for everyone who finished, then open voting."""
        try:
            members, city = job["members"], job["city"]
            query = create_group_search_query(members, city)
            places = find_places(query, city)
            if len(places) < 3 and query != BROAD_QUERY:
                extra = find_places(BROAD_QUERY, city)
                seen = {p.get("place_id") or p.get("name") for p in places}
                places = places + [p for p in extra if (p.get("place_id") or p.get("name")) not in seen]
            # No "when" in group mode yet: each card shows today's hours.
            places, _ = annotate(places, "", job.get("tz"))
            results = choose_group_places(members, places, city, limit=3)
            store.save_results(room_id, results)
        except Exception:
            log.exception("Group search failed for room %s", room_id)
            store.search_failed(room_id)

    @router.post("")
    def create(req: CreateRequest):
        name, city = req.name.strip(), req.city.strip()
        if not name or not city:
            return JSONResponse(status_code=422, content={"detail": "Please enter your name and a city."})
        try:
            return store.create_room(name, city, req.tz.strip())
        except GroupError as e:
            return _error(e)

    @router.post("/join")
    def join(req: JoinRequest):
        if not req.name.strip():
            return JSONResponse(status_code=422, content={"detail": "Please enter your name."})
        try:
            return store.join_room(req.code, req.name.strip())
        except GroupError as e:
            return _error(e)

    @router.get("/{room_id}")
    def state(room_id: str, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            return store.state(room_id, me["id"])
        except GroupError as e:
            return _error(e)

    @router.post("/{room_id}/start")
    def start(room_id: str, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            store.start(room_id, me)
            return store.state(room_id, me["id"])
        except GroupError as e:
            return _error(e)

    @router.post("/{room_id}/turn")
    def turn(room_id: str, req: TurnRequest, background: BackgroundTasks, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            history, pending, done = store.answer_and_get_pending(
                room_id, me["id"], req.question.strip(), req.answer.strip()
            )
            if done:
                # Last one to finish kicks off the search for everyone.
                if store.everyone_done(room_id):
                    job = store.begin_search(room_id)
                    if job:
                        background.add_task(run_search, room_id, job)
                return {"done": True}
            if pending is None:
                room = store.state(room_id, me["id"])
                question = ask_question(history, [], {"city": room["city"], "group": True})
                question = {k: question[k] for k in ("question", "options", "placeholder") if k in question}
                pending = store.set_pending(me["id"], question)
            return {"done": False, "number": len(history) + 1, **pending}
        except GroupError as e:
            return _error(e)

    @router.post("/{room_id}/search")
    def search_now(room_id: str, background: BackgroundTasks, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            job = store.begin_search(room_id, member=me)
            if job:
                background.add_task(run_search, room_id, job)
            return store.state(room_id, me["id"])
        except GroupError as e:
            return _error(e)

    @router.post("/{room_id}/vote")
    def vote(room_id: str, req: VoteRequest, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            store.vote(room_id, me["id"], req.index)
            return store.state(room_id, me["id"])
        except GroupError as e:
            return _error(e)

    @router.post("/{room_id}/reveal")
    def reveal(room_id: str, x_member_token: str = Header("")):
        try:
            me = store.authenticate(room_id, x_member_token)
            store.reveal(room_id, me)
            return store.state(room_id, me["id"])
        except GroupError as e:
            return _error(e)

    return router
