# Demo Video Script — 3 minutes

A storyboard for a 3-minute Loom (or any screen-recording tool) demonstration of the project. Optimised for the application portfolio: an evaluator should walk away knowing **what was built, that it works, and why it matters**, without ever pausing the video.

## Pre-flight checklist (do this once, before recording)

- [ ] `uvicorn app.main:app --reload --port 8000` running in a separate terminal — visible in screen
- [ ] Firebase ID token freshly grabbed (token lives 1h; record in one take to be safe)
- [ ] `claude_desktop_config.json` updated with the fresh token; Claude Desktop restarted
- [ ] Claude Desktop opened, fresh chat, tool icon visible at the bottom of the input area
- [ ] Browser tab open with `github.com/Arditthaqi/buchhaltiq-mcp` for the closing shot
- [ ] Microphone tested. Camera off (this is a code demo, not a face cam).
- [ ] Loom set to 1080p. Cursor highlight on.

## Three-minute timeline

| Time | What's on screen | What you say |
|---|---|---|
| **0:00–0:15** | Claude Desktop, blank chat. Title overlay: *"buchhaltiq-mcp — Claude meets German bookkeeping"* | "I built an MCP server that connects Claude Desktop directly to my own German accounting SaaS — BuchhaltIQ. In the next three minutes you'll see Claude pull real data from my actual restaurant, categorise transactions correctly to DATEV accounts, and generate a monthly P&L. Let's go." |
| **0:15–0:45** | Slide / overlay: six-bullet list of the Bewirtung deduction rules (or just bullet them on screen). | "Bookkeeping in Germany is rules-density on top of rules-density. The Bewirtungs-deduction alone has six layers: 70% deductible income-tax-side, but 100% VAT recoverable, mandatory hand-written note, different SKR03 vs SKR04 accounts, flips to 100% for employee events. Existing tools route this through dropdowns. **LLMs with the right tools route this through one sentence.**" |
| **0:45–1:25** | Claude Desktop. Type slowly. | Type: `Wie war mein April 2026? Erklär mir auch die Einnahmequellen und DATEV-Bereitschaft.` <br><br>While Claude responds, narrate: "Claude is calling `accounting_month_overview` against my live backend. The response separates Tagesberichte, invoice payments, standalone income, P&L expenses, VAT estimate, missing receipts, and DATEV readiness. That is the difference between a generic P&L total and a product-aware accounting assistant." |
| **1:25–2:05** | Claude Desktop, same chat. | Type: `Wenn ich 238,45 € Wareneinkauf bar einkaufe — wie buche ich das in SKR03?` <br><br>Narrate: "One sentence in. Claude calls three tools — `extract_vat_from_receipt`, `validate_datev_account`, `resolve_account_assignment`. It comes back with the complete DATEV booking: Soll 3400, Haben 1000 — Kasse, because I said cash. BU-Schlüssel 9. Net 200,38€. VAT 38,07€. Ready to enter into DATEV." |
| **2:05–2:35** | Claude Desktop, same chat. | Type: `Such mir alle METRO-Belege im April und sortier sie nach Betrag.` <br><br>Narrate: "And the multi-step example — Claude calls `search_belege` with the substring filter, gets the real bank transactions back, sorts them client-side. Five METRO purchases, 1.389€ total. **No SQL, no clicks. One sentence.**" |
| **2:35–2:55** | Switch to GitHub repo. README visible. | "Behind this — fifteen tools across ten Python modules. Two modes per tool: demo mode runs on JSON fixtures so the public repo is GDPR-safe, production mode talks to the real backend. Same tool definitions in both, no drift. 126 tests, all green. Architecture writeup, privacy doc, end-to-end case study all live in the repo." |
| **2:55–3:00** | GitHub repo URL highlighted. | "Code, case study, and the four-tool live walkthrough are in the repo. Thanks for watching." |

## What to **not** say

- "I'm applying for…" / "I'd love to work at…" — that belongs in the cover letter, not the demo.
- "This is just a prototype" / "rough edges" — undersells. The repo is shipped, tested, validated.
- Don't read the JSON output line by line. **Narrate what it means**, let the screen show the data.

## Post-production

- Cut any pause longer than 1.5s.
- Caption the three Claude prompts on screen so a muted viewer still gets the shape.
- Final 5 frames: a static URL card with the GitHub link.

## One-take versus edited

The first time, do it as a single take so you internalise the flow. The second time, edit if needed — but a single confident take with the cursor focused beats a polished edit with hesitation in the narration.

## Backup plan if a tool errors mid-demo

- If a tool returns an empty result: pivot to *"and you can see the response gracefully handles missing data"* — do not break flow.
- If the backend connection drops: switch to demo mode (`BUCHHALTIQ_MCP_MODE=demo`) — the queries still produce real-looking results from fixtures. Mention this in passing: *"this is exactly why we ship a demo mode — fully reproducible, even when the backend is offline."*
