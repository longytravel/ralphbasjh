#!/bin/bash
# Ralph Loop for Claude Code - Windows Compatible
# Run with Git Bash: ./ralph-loop.sh "Your task description"

set -e

# Configuration
MAX_ITERATIONS=${MAX_ITERATIONS:-50}
COMPLETION_MARKER="<promise>COMPLETE</promise>"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check for task argument or plan.md
if [ -n "$1" ]; then
    TASK="$1"
elif [ -f "plan.md" ]; then
    TASK="Follow the plan in plan.md"
else
    echo -e "${RED}Error: Provide a task as argument or create a plan.md file${NC}"
    echo "Usage: ./ralph-loop.sh \"Your task description\""
    exit 1
fi

# Initialize progress file if it doesn't exist
if [ ! -f "progress.txt" ]; then
    echo "# Progress Log" > progress.txt
    echo "Started: $(date)" >> progress.txt
    echo "---" >> progress.txt
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Ralph Loop for Claude Code${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Task:${NC} $TASK"
echo -e "${YELLOW}Max iterations:${NC} $MAX_ITERATIONS"
echo ""

for i in $(seq 1 $MAX_ITERATIONS); do
    echo -e "${GREEN}--- Iteration $i of $MAX_ITERATIONS ---${NC}"

    # Check for blocking file
    if [ -f "RALPH-BLOCKED.md" ]; then
        echo -e "${RED}Blocked! Found RALPH-BLOCKED.md - stopping loop${NC}"
        exit 1
    fi

    # Build the prompt
    PROMPT="You are in a Ralph Loop iteration $i.

TASK: $TASK

INSTRUCTIONS:
1. Read plan.md to find the NEXT unchecked task (marked with '- [ ]').
2. Read progress.txt to see what's already been done.
3. **CRITICAL: Read PRD.md for implementation details** - use the exact:
   - Data models and JSON schemas (Section 6)
   - Configuration parameters (Section 5 and 12)
   - Step specifications (Section 3)
   - Gate thresholds and formulas (Section 4)
4. Implement the task fully, following PRD specs precisely.
5. Run tests to verify your work.
6. If successful:
   - Update plan.md: change '- [ ]' to '- [x]' for the completed task
   - Update progress.txt with iteration details
   - Commit changes with message: 'ralph: [brief description]'
7. IMPORTANT: Only do ONE task per iteration, then exit.
8. If ALL tasks in plan.md are checked '[x]', output exactly: $COMPLETION_MARKER

Files for context: @plan.md @progress.txt @PRD.md

CRITICAL: PRD.md is your source of truth. Every implementation must match the PRD specifications exactly - data models, formulas, thresholds, file structures, etc."

    # Run Claude Code
    echo -e "${YELLOW}Running Claude Code...${NC}"

    # Use claude with print mode to capture output, allow edits
    if claude --dangerously-skip-permissions -p "$PROMPT" 2>&1 | tee output.log; then
        echo -e "${GREEN}Claude completed iteration $i${NC}"
    else
        echo -e "${RED}Claude exited with error on iteration $i${NC}"
    fi

    # Check for completion marker
    if grep -q "$COMPLETION_MARKER" output.log 2>/dev/null; then
        echo ""
        echo -e "${GREEN}========================================${NC}"
        echo -e "${GREEN}   TASK COMPLETE!${NC}"
        echo -e "${GREEN}========================================${NC}"
        echo "Completed in $i iterations"
        echo "Finished: $(date)" >> progress.txt
        exit 0
    fi

    # Brief pause between iterations
    sleep 2
done

echo -e "${YELLOW}Reached maximum iterations ($MAX_ITERATIONS)${NC}"
echo "You may need to continue manually or increase MAX_ITERATIONS"
