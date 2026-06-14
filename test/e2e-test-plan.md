# End-to-end test plan

Full-stack verification of the single Docker container (frontend built and served by the FastAPI
backend on `:8000`), driven with Playwright against a **real OpenRouter LLM** (`gpt-5.4-nano`) and a
**real Supabase** database. Items map to **SPEC.md** ("Success Criteria", "Testing") and
**CONTRACT.md** (§7, §8, §10, §12). This is the integration tie-breaker: the whole 3-way experience
(visitor, Avatar, human) must work together.

Cost & cleanup rules (SPEC "Testing"): set `MODEL=openai/gpt-5.4-nano` to keep LLM costs low; it is
fine to call the model and write test conversations. When finished, **delete every screenshot** and
**delete all test conversation threads** created in Supabase, then check off the cleanup items.

SPEC traceability is noted per section. The orchestrator runs the container and checks boxes here
last, after the backend and frontend plans pass.

---

## 1. Container build & boot (SPEC tech stack / single container; CONTRACT §8, §12)

- [x] `scripts/start_pc.ps1` (or `start_mac.sh`) stops any running container, rebuilds the image, and starts it.
- [x] The container builds the frontend (`dist/`) and serves it from the backend in one image.
- [x] The app is reachable at `http://localhost:8000/` (visitor) and `http://localhost:8000/admin`.
- [x] `/` serves the built `index.html`; `/admin` serves `admin.html`; `/assets/*` load with 200s.
- [x] `GET /api/config` returns the live `owner_name` + `model`; the visitor header shows the owner name.
- [x] The Supabase connectivity check (`backend/tests/test_supabase_connection.py`) passes against the real DB before E2E proceeds.
- [x] `scripts/stop_pc.ps1` (or `stop_mac.sh`) cleanly stops the container.

## 2. Visitor streaming reply — real LLM (SPEC interactive chat + Q&A #9; CONTRACT §4, §7)

- [x] Sending a real question streams the Avatar's reply token-by-token into a `.msg--avatar` bubble.
- [x] The reply is on-topic for Emil / E&P Systems (uses the knowledge base, first person as the twin).
- [x] A question that maps to a FAQ triggers a `faq_tool` `.tool-line` (cyan) during the stream.
- [x] The avatar message is persisted in Supabase with role=avatar and any `tool_calls`.
- [x] After the reply completes, the composer regains focus.

## 3. Qn instant answer — no LLM (SPEC; CONTRACT §7 step 4)

- [x] Typing `Q2` returns FAQ #2 immediately with the `.qn-tag` on the visitor turn and **no** LLM latency/tool line.
- [x] The reply restates the question (`**Q2:** …`) then gives the answer.
- [x] Exactly two rows (visitor + avatar) are written to Supabase for the Qn exchange.

## 4. `?q` deep link (SPEC; CONTRACT §10)

- [x] Opening `http://localhost:8000/?q=2` auto-submits `Q2` on arrival and shows the answer.
- [x] The `?q` param is removed from the address bar after submission.

## 5. Multi-user isolation (SPEC "multiple users with different conversation_ids")

- [x] Two browser contexts get **distinct** `conversation_id`s.
- [x] Each context sees only its own thread; messages do not leak between conversations.
- [x] Both conversations appear as separate rows in the admin inbox.

## 6. Human joins from admin → appears in visitor poll (SPEC Q&A #4, #5; CONTRACT §7)

- [x] Admin logs in, opens a visitor's conversation, and posts a reply "as {OWNER_NAME}".
- [x] The owner message renders in admin as a `.msg--human` bubble.
- [x] Within one poll interval (~10s) the visitor's page shows the human message as a `.msg--human` bubble (ring + tint + glow + "{OWNER_NAME} — live"), with no reload.
- [x] The Avatar does **not** auto-react to the human message.
- [x] The next time the visitor sends a message, the human's line is present in the transcript (the Avatar acknowledges/continues in context).

## 7. push_tool → needs-attention + Pushover (SPEC reference push.py + Q&A #5; CONTRACT §6, §7)

- [x] A visitor request that needs a human (e.g. asks to get in touch and provides an email, or asks something unanswerable) causes `push_tool` to fire.
- [x] During the stream a `.tool-line--push` (yellow) appears and the bubble states the owner was notified.
- [x] A real Pushover notification is delivered (creds present) — verified on the device/log.
- [x] The avatar row is stored with `needs_attention=true`; the conversation flips to **needs-attention** in the admin inbox (yellow row + bell-dot).
- [x] Opening that thread in admin clears `needs_attention` and marks all rows read.

## 8. Admin read/unread lifecycle (SPEC Q&A #5; CONTRACT §2, §7)

- [x] A fresh visitor message makes the conversation **unread** in the inbox (dot + stronger text).
- [x] Opening the thread marks all rows read (single round-trip) and the unread state clears.
- [x] Reopening shows no unread/needs-attention residue.

## 9. Rate limit 429 end-to-end (SPEC Q&A #12; CONTRACT §7 step 1)

- [x] Sending >20 messages within a minute on one `conversation_id` yields an HTTP 429.
- [x] The visitor UI shows a friendly "sending messages too quickly" line (no crash).
- [x] No LLM call or visitor row is created for the rejected request.
- [x] A different `conversation_id` is unaffected at the same time.

## 10. Admin auth gating in the live app (SPEC Q&A #6; CONTRACT §7, §9)

- [x] Hitting any `/api/admin/*` data route without logging in returns 401 (verified via the network tab / direct request).
- [x] The admin UI shows the login `.card` until a correct password is entered.
- [x] Logging out returns to the locked state and re-blocks the data routes.

## 11. Theme & responsive across the live app (SKILL acceptance; ux-flows)

- [x] Visitor and admin both render correctly in **dark** and **light** against the live backend.
- [x] Visitor works at 360px (single column, docked composer) and on desktop.
- [x] Admin collapses to master/detail at 360px with a working back control; desktop side-by-side intact.

## 12. Resilience / edge (CONTRACT §8; SPEC abuse guards)

- [x] A >20,000-char message is truncated (note appended) and the Avatar still replies sensibly.
- [x] Reloading the visitor page with Keep chat on restores the full thread from the DB.
- [x] Reset assigns a new `conversation_id` and starts an empty thread.
- [x] No unhandled 500s appear in the container logs during the full run.

## 13. Screenshots (capture during E2E, delete in cleanup)

- [x] Visitor streaming reply (dark, desktop).
- [x] Visitor with `faq_tool` tool line (dark).
- [x] Visitor with `push_tool` line + "notified {OWNER_NAME}" (dark).
- [x] Visitor with a `.msg--human` reply from the owner (dark + light).
- [x] Visitor `Qn` instant answer (dark).
- [x] Visitor 360px (dark + light).
- [x] Admin inbox with unread + needs-attention rows (dark).
- [x] Admin open thread + owner reply composer (dark + light).
- [x] Admin master/detail at 360px (dark).
- [x] Admin login card (dark + light).

## 14. Cleanup (SPEC "Testing" — mandatory)

- [x] All E2E screenshots deleted from disk.
- [x] All test conversation threads created during E2E deleted from Supabase (no test rows left in `messages`).
- [x] `MODEL` confirmed: `.env` is `openai/gpt-5.4-nano` (this owner's dev/test default; switch to `openai/gpt-5.4-mini` for production per the README).
- [x] The test container stopped (`stop_pc.ps1` / `stop_mac.sh`).
- [x] All boxes in this plan, the backend plan, and the frontend plan checked off.
