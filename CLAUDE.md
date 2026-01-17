# EA Stress Test System - Development Context

## Automatic Bootstrap Instructions

When starting a session (or after /clear), follow these steps:

### 1. Read State Files
- **plan.md** - Contains all tasks with checkboxes `[ ]` (pending) and `[x]` (complete)
- **progress.txt** - Detailed log of completed iterations
- **PRD.md** - Full specification with data models, schemas, formulas

### 2. Identify Next Task
Find the first unchecked item `- [ ]` in plan.md - that's your next task.

### 3. Implement Following PRD Specs
Always reference PRD.md for:
- Data models (Section 6)
- Configuration parameters (Section 5 & 12)
- Step specifications (Section 3)
- Gate thresholds and formulas (Section 4)

### 4. After Completing Each Task
1. Mark task complete in plan.md: `- [ ]` → `- [x]`
2. Add entry to progress.txt with details
3. Commit changes: `git add -A && git commit -m "ralph: [task description]"`

### 5. Context Management
When context gets large:
- User will run `/clear`
- You'll reload with fresh context
- Read these files again and continue
- All state is in files - nothing is lost

## Current Project
Building a 14-step EA validation workflow for MetaTrader 5.
See plan.md for task list, PRD.md for full requirements.

## Quick Start Command
After reading this, say: "I've loaded context from files. [X] tasks complete, next task: [task name]"
