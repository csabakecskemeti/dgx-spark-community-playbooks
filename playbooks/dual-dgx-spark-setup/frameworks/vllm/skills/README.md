# Claude Code Skills for vLLM on DGX Spark

Automated skills for controlling dual DGX Spark vLLM infrastructure via Claude Code.

## Overview

These skills allow Claude Code to manage the full lifecycle of distributed vLLM inference:

```
┌─────────────┐     SSH      ┌─────────────┐     RDMA     ┌─────────────┐
│    Mac      │─────────────▶│  Spark 1    │◀────────────▶│  Spark 2    │
│ (Claude)    │              │  (Head)     │              │  (Worker)   │
└─────────────┘              └─────────────┘              └─────────────┘
```

## Installation

1. **Copy skills to Claude Code skills directory:**
   ```bash
   mkdir -p ~/.claude/skills/
   cp spark-*.md ~/.claude/skills/
   ```

   Or copy each to its own folder:
   ```bash
   for skill in spark-start spark-stop spark-load spark-bench spark-status; do
     mkdir -p ~/.claude/skills/$skill
     cp ${skill}.md ~/.claude/skills/$skill/SKILL.md
   done
   ```

2. **Create `.env` configuration:**
   ```bash
   cp .env.example playbooks/dual-dgx-spark-setup/.env
   # Edit with your settings
   ```

3. **Verify SSH access:**
   ```bash
   ssh spark1.local hostname
   ssh spark2.local hostname
   ```

## Available Skills

| Skill | Description | Usage |
|-------|-------------|-------|
| `spark-start` | Start containers + Ray cluster | `/spark-start` |
| `spark-stop` | Stop everything cleanly | `/spark-stop` |
| `spark-load` | Load a model into vLLM | `/spark-load Qwen/Qwen3-235B-A22B-GPTQ-Int4` |
| `spark-bench` | Run benchmark | `/spark-bench` |
| `spark-status` | Check infrastructure status | `/spark-status` |

## Usage Examples

### Start Infrastructure
```
> /spark-start
```

### Load a Model
```
> /spark-load Qwen/Qwen3-235B-A22B-GPTQ-Int4
> /spark-load Qwen/Qwen3-235B-A22B-GPTQ-Int4 --enforce-eager
```

### Run Benchmark
```
> /spark-bench
```

### Check Status
```
> /spark-status
```

### Stop Everything
```
> /spark-stop
```

## Configuration

All skills read from `playbooks/dual-dgx-spark-setup/.env`:

```bash
# DGX Spark Hosts
SPARK1_HOST=spark1.local
SPARK2_HOST=spark2.local

# RDMA Network
SPARK1_RDMA_IP=192.168.200.3
SPARK2_RDMA_IP=192.168.200.13
RDMA_INTERFACE=enp1s0f1np1

# Container Settings
VLLM_CONTAINER=nvcr.io/nvidia/vllm:26.03-py3
CONTAINER_NAME=vllm-spark

# vLLM Defaults
DEFAULT_GPU_MEM=0.7
DEFAULT_MAX_MODEL_LEN=32768

# Benchmark Defaults
BENCH_INPUT_LEN=2048
BENCH_OUTPUT_LEN=2000
BENCH_NUM_PROMPTS=50
BENCH_REQUEST_RATE=10
```

## Skill Details

### spark-start

Starts Docker containers on both Sparks with all required RDMA/NCCL environment variables, then initializes a Ray cluster.

**Key operations:**
1. Start container on Spark 1 (head)
2. Start container on Spark 2 (worker)
3. Start Ray head on Spark 1
4. Start Ray worker on Spark 2
5. Verify cluster shows 2 GPUs

### spark-load

Loads a model into vLLM with tensor parallelism across both GPUs.

**Arguments:**
- Model name (required): e.g., `Qwen/Qwen3-235B-A22B-GPTQ-Int4`
- `--enforce-eager`: Disable compilation (optional)
- `--gpu-mem <value>`: Override GPU memory utilization (optional)

**Note:** Large models (200B+) take 15-30 minutes to load.

### spark-bench

Runs `vllm bench serve` and records results to `benchmarks/RESULTS.md`.

### spark-status

Checks:
- Container status on both Sparks
- Ray cluster status
- vLLM server health
- Loaded models

### spark-stop

Cleanly shuts down:
1. Ray processes on both nodes
2. Docker containers on both nodes

## Troubleshooting

### SSH Connection Failed
```bash
# Check SSH config
cat ~/.ssh/config

# Test connection
ssh -v spark1.local hostname
```

### Container Already Exists
```bash
# Remove existing container
ssh spark1.local "docker rm -f vllm-spark"
ssh spark2.local "docker rm -f vllm-spark"
```

### Model Not Loading
Check logs:
```bash
ssh spark1.local "docker exec vllm-spark tail -50 /tmp/vllm.log"
```
