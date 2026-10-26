# Organizer exercises (S-06 / P1-02)

Owner: Saif. Status: **protocol ready, sessions not run yet** (they need 3–5 real organizers or
representative users; nobody has been observed so far). Backend issues found go to Ridwan.

## Who

3–5 people who plan or run events or buildings: an event organizer, a venue or facilities
manager, a school or hospital safety lead, a student society that runs events. Not the team.
Record only first names or P1–P5; no recordings without written consent.

## Setup (per session, about 45 minutes)

1. Start the app with a live model and the simulator: set the three OpenRouter lines in `.env`
   (README quickstart) or the Nebius ones, then `make up`. Check the header badge is green and `/welcome` shows every row ready.
2. Fresh browser profile, 1600 × 900 or the participant's own laptop. Close other tabs.
3. The observer has this page and a timer; one person observes, one takes notes. Do not help
   unless the participant is stuck for 2 minutes; then give the smallest hint and note it.

## The task (read it out, then stay quiet)

> "You are planning an event in a real building. Use Showtime to build the venue from the map,
> test the plan, decide which changes to accept, and download the checklist you would give your
> stewards. Think aloud as you go."

Suggested venue: their own building, else a school or hospital near them, 3–4 floors.

| Step | Done when | Time it |
| --- | --- | --- |
| T1 Map building | The venue is built from the map (floors, used as, inside set) and they pressed "Use this venue" | ✓ |
| T2 Check | Doors and headcounts look right to them; at least one correction made | ✓ |
| T3 Test | "Test this plan" started and Your plan appeared | ✓ |
| T4 Read the verdict | They can say in their own words what the badge means ("Not confirmed" / "Partly confirmed") — ask after T4 | ✓ |
| T5 Accept | They chose which changes to keep and accepted them (or decided not to, with a reason) | ✓ |
| T6 Checklist | The checklist is downloaded and they say who they would hand it to | ✓ |

## What to record (copy this table per participant)

| Field | P_ |
| --- | --- |
| Role, experience | |
| Venue used | |
| T1 time / hints / errors | |
| T2 time / corrections made / confusion | |
| T3 time / did the test start on first click? | |
| T4 their explanation of the verdict badge (verbatim) | |
| T4 understood? (yes / partly / no) | |
| T5 time / what they kept and why | |
| T6 time / who gets the checklist | |
| Failures (crash, error message, stuck > 2 min) | |
| Quotes | |
| Would they use it? For what? | |

## After each session

- Copy every confusion and failure into the issue list below with a severity: **blocker** (task
  not possible), **major** (needed a hint), **minor** (slowed them down), **polish**.
- Backend issues (wrong numbers, failed runs, map import) → Ridwan; screens and copy → Saif.

## Prioritized issue list

| # | Issue | Seen by | Severity | Owner | Fixed in | Re-checked |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## Correction round

Fix the blockers and majors, then run one more session (a new participant, or one from the first
round on a different venue) and record whether each fixed issue still occurs. Only then does the
usability claim go into the README or the submission.
