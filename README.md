# Reach

Voice-controlled assistive robotics kit — prototype code. Product spec: PRD v2 (2026-10-23). Arm setup: [../SETUP_ARMS.md](../SETUP_ARMS.md).

**Status: everything runs against mocks.** No skill has passed physical validation, no perception, voice, LLM or telephony provider is wired in, and nothing in this repo moves the real arm yet.

## Run

```bash
conda activate lerobot
cd ~/iReach/reach
pip install -e ".[dev]"
python3 -m pytest -q
python3 scripts/run_mock_demo.py
```

The demo runs the PRD's primary flow on the mock robot: remember → restart → open drawer with hook → return hook → find → pick → hand off → call caretaker → relay → P1 task offer.

## Layout

| Path | Owns | State |
|---|---|---|
| `config/*.yaml` | robot ports & limits, cameras, tools/rack, semantic locations, skill waypoints, caretakers | ports/ids verified; poses and waypoints are placeholders |
| `reach/results.py` | `ActionResult` envelope, status and reason codes (PRD 7.3) | done |
| `reach/logging.py` | JSONL `EventLog` with subscribers for the dashboard | done |
| `reach/hardware/` | `ArmDriver` interface, `MockArm`, `LeRobotArm` (real follower), `MockWorld` | real driver written, untested on hardware |
| `reach/calibration/` | joint limits from the LeRobot calibration file | done; camera calibration TODO |
| `reach/kinematics/` | FK/IK, frames | TODO (skills use joint waypoints for now) |
| `reach/motion/` | `StopLatch`, `SafetyGate` (limits minus margin, step cap), `MotionExecutor` (single motion owner) | done |
| `reach/tools/` | tool registry, attachment state incl. unknown, verified exchange | done |
| `reach/skills/` | drawer, pick/place, spoon, docking; precondition → trajectory → perception check | mock effects only |
| `reach/perception/` | observation/detection types, `MockPerception` | real cameras TODO |
| `reach/memory/` | SQLite location memory with provenance history | done |
| `reach/comms/` | caretaker registry, update builder, relay store, phone-agent toolset, `MockTelephony` | provider TODO |
| `reach/agent/` | `ReachTools` (PRD 7.2 tools) and deterministic `flows` | LLM planner TODO |
| `reach/voice/` | `Speaker` interface, console and scripted speakers | STT/TTS TODO |
| `reach/dashboard/` | — | framework unresolved |

## Safety rules built into the code

- Only `MotionExecutor` writes joint targets. It rejects (never clamps) targets within `limit_margin` of the calibrated limits, splits moves into `max_step` increments, and checks the stop latch before every step.
- The stop latch needs an explicit `reset()`; nothing replays the interrupted motion.
- A skill with `validated: false` in `skills.yaml` refuses to run when the arm is not the mock.
- Success requires a fresh perception check, not just a completed trajectory. Unverifiable steps report `verified=False`.
- Tool identity becomes `unknown` after any failed or interrupted exchange; dependent skills then refuse until someone checks.
- Calls go only to registered caretakers, after the user approves the preview, once. Caretaker replies become relay records; a task suggestion survives only if it is allowlisted, and only the local user's "yes" can start motion, through the normal flow.

## Next steps (PRD section 10)

1. Hardware wiring in `app.py` (`LeRobotArm` + real perception), behind explicit approval for every motion run.
2. Cameras and calibration (Gates 1–2), then real `Perception`.
3. Measure rack, drawer, bowl and pad poses; replace waypoints and flip `validated` per skill as Gates 4–6 pass.
4. LLM planner over `ReachTools`; voice; dashboard; telephony provider.
