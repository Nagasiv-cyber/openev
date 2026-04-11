---
title: OpenEnv Code Review
emoji: 🛡️
colorFrom: blue
colorTo: green
sdk: docker
app_file: app.py
pinned: false
---

# 🛡️ CyberGuard Code Review — OpenEnv Environment

> **Meta × Scaler AI Hackathon Submission**  
> An AI-powered security code review benchmark built on [OpenEnv](https://openenv.dev).

---

## 🌐 Live Demo

| Link | Description |
|------|-------------|
| [🔗 Hugging Face Space](https://huggingface.co/spaces/visaaaaa/openenv-arbitrage) | Live deployed environment |
| [📘 API Docs](https://visaaaaa-openenv-arbitrage.hf.space/docs) | Interactive Swagger UI |
| [📦 GitHub Repo](https://github.com/Nagasiv-cyber/openev) | Source code |

---

## 🎯 Environment Overview

**CyberGuard Code Review** is a reinforcement learning environment where an AI agent acts as a security code reviewer. Given a stream of code snippets across three difficulty tiers (easy / medium / hard), the agent must:

1. **APPROVE** — if the code is safe
2. **REJECT** — if the code contains a vulnerability
3. Optionally assign a **severity** (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
4. Optionally provide a **comment** explaining the decision

---

## 🏗️ Architecture

```
Agent (LLM)
    │
    ▼  POST /reset?task_id=easy
    │  POST /step/{session_id}  { action, severity, comment }
    │  GET  /state/{session_id}
    │  GET  /grade/easy/{session_id}
    ▼
FastAPI Server (app.py)
    │
    ▼
CodeReviewEnvironment (environment.py)
    │
    ├── Snippet Library (60 code snippets)
    ├── Per-step Reward Scoring
    └── Trajectory Grader (non-linear adjustments)
```

---

## 📊 Scoring System

### Per-Step Raw Rewards

| Scenario | Score |
|----------|-------|
| ✅ Correct action + correct severity + comment | **0.90** *(Perfect)* |
| ✅ Correct action + severity or comment | **0.88** *(Near-perfect)* |
| ✅ Correct on Hard, partial explanation | **0.70–0.87** *(Partial)* |
| ⚠️ Rejected safe code (overcautious) | **0.50** |
| ❌ Ignored a real vulnerability | **0.30** |
| ❌ Flagged safe code as vulnerable | **0.15** |
| 💥 Approved a vulnerable snippet | **0.10** *(Catastrophic)* |

> All rewards are in the range **[0.10, 0.99]** inclusive.

### Trajectory Grader Modifiers

| Modifier | Easy | Medium | Hard |
|----------|------|--------|------|
| 💥 Penalty per approved bug | -0.40 | -0.50 | -0.60 |
| 🎯 Consistency bonus (≥80% correct) | +0.05 | +0.10 | +0.15 |
| 📝 Explanation bonus (≥80% perfect) | +0.03 | +0.07 | +0.10 |

---

## 🔌 API Endpoints

```
GET  /              → Web dashboard
GET  /health        → Health check
GET  /validate      → Evaluator compliance check
POST /reset         → Start new episode (param: task_id=easy|medium|hard)
POST /step/{id}     → Submit review decision
GET  /state/{id}    → Get full episode state
GET  /grade/easy/{id}   → Easy grader score
GET  /grade/medium/{id} → Medium grader score
GET  /grade/hard/{id}   → Hard grader score
GET  /docs          → Interactive Swagger UI
```

---

## ✅ Validation Results

### Local Simulation Output

```
============================================================
  CyberGuard Code Review — GRADER SIMULATION
============================================================

[EASY  ] Score: 0.88  | Steps: 5 | Correct: 5/5 | Bugs missed: 0
[MEDIUM] Score: 0.76  | Steps: 5 | Correct: 4/5 | Bugs missed: 1
[HARD  ] Score: 0.52  | Steps: 5 | Correct: 3/5 | Bugs missed: 2

All scores within required [0.10, 0.99] range ✅
```

### Server Health Check

```bash
$ curl https://visaaaaa-openenv-arbitrage.hf.space/health
{"status":"healthy","service":"code-review-environment"}

$ curl https://visaaaaa-openenv-arbitrage.hf.space/validate
{"status":"valid","message":"Environment is strictly compliant with Phase 2 validation.","grader_endpoints":["/grade/easy/{session_id}","/grade/medium/{session_id}","/grade/hard/{session_id}"]}
```

---

## 🚀 Quick Start

### 1. Run Locally

```bash
git clone https://github.com/Nagasiv-cyber/openev.git
cd openev
pip install fastapi uvicorn pydantic
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### 2. Run a Full Episode

```python
import requests

BASE = "http://localhost:8000"

# Start episode
obs = requests.post(f"{BASE}/reset?task_id=easy").json()
session_id = obs["session_id"]

# Review loop
while not obs["done"]:
    obs = requests.post(f"{BASE}/step/{session_id}", json={
        "action": "REJECT",
        "severity": "HIGH",
        "comment": "Unsanitized user input — SQL Injection risk."
    }).json()
    print(f"Step reward: {obs['reward']}")

# Get final grade
grade = requests.get(f"{BASE}/grade/easy/{session_id}").json()
print(f"Final score: {grade['score']}")
```

### 3. Simulate All Graders

```bash
python simulate_grader.py
```

---

## 📁 File Structure

```
openev/
├── app.py              # FastAPI server — all endpoints
├── environment.py      # Core RL environment & scorer
├── inference.py        # OpenEnv agent inference script
├── models.py           # Pydantic/dataclass models
├── simulate_grader.py  # Local grader simulation
├── openenv.yaml        # OpenEnv task configuration
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container definition
└── README.md           # This file
```

---

## 🧪 OpenEnv Compliance

| Requirement | Status |
|-------------|--------|
| ≥ 3 tasks with graders | ✅ Easy, Medium, Hard |
| Score strictly in (0, 1) | ✅ Clamped to [0.10, 0.99] |
| Unique grader endpoints | ✅ `/grade/easy`, `/grade/medium`, `/grade/hard` |
| `spec_version: 1.0` in YAML | ✅ |
| Docker-based deployment | ✅ |
| Agent inference script | ✅ `inference.py` |

---

*Built for the **Meta × Scaler India's Biggest AI Hackathon** — OpenEnv Track* 🚀
