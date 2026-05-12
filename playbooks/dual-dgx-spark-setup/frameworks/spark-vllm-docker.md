# spark-vllm-docker Setup

Community-maintained vLLM container optimized for DGX Spark with nightly builds. Use this for newer models (Qwen 3.6+) that require recent vLLM versions.

**Repository:** https://github.com/eugr/spark-vllm-docker

## Why Use This?

Build a container with latest vLLM to support the newest models (e.g., Qwen 3.6).

## Placeholder Reference

Throughout this document, replace these placeholders with your values:

| Placeholder | Description | How to Find |
|-------------|-------------|-------------|
| `<SPARK1_HOST>` | Hostname of head node | Your hostname (e.g., `spark1.local`) |
| `<SPARK2_HOST>` | Hostname of worker node | Your hostname (e.g., `spark2.local`) |
| `<SPARK1_RDMA_IP>` | RDMA IP of head node | Run: `ip addr show <RDMA_INTERFACE>` |
| `<SPARK2_RDMA_IP>` | RDMA IP of worker node | Run: `ip addr show <RDMA_INTERFACE>` |
| `<RDMA_INTERFACE>` | Network interface for RDMA | Run: `ip link` (e.g., `enp1s0f1np1`) |
| `<ROCE_DEVICES>` | RoCE device names | Run: `ibdev2netdev` (use left column, comma-separated) |

## Environment Configuration (.env)

The `spark-vllm-docker` repo uses a `.env` file for cluster configuration. This file controls RDMA settings, container naming, and NCCL tuning.

### Complete .env Template

```bash
# =============================================================================
# spark-vllm-docker Environment Configuration
# =============================================================================
# Copy this to ~/spark-vllm-docker/.env and replace placeholders with your values

# -----------------------------------------------------------------------------
# CLUSTER NODES
# -----------------------------------------------------------------------------
# Comma-separated RDMA IP addresses (head node FIRST)
# For single Spark: just one IP
# For dual Spark: head,worker
CLUSTER_NODES=<SPARK1_RDMA_IP>,<SPARK2_RDMA_IP>

# -----------------------------------------------------------------------------
# NETWORK INTERFACES
# -----------------------------------------------------------------------------
# Ethernet interface name (find with: ip link)
ETH_IF=<RDMA_INTERFACE>

# RoCE device names - CRITICAL: use device names, NOT interface names!
# Find with: ibdev2netdev (use LEFT column values)
# Example output:
#   rocep1s0f0 port 1 ==> enp1s0f0np0
#   rocep1s0f1 port 1 ==> enp1s0f1np1
# Use: rocep1s0f0,rocep1s0f1 (NOT enp1s0f0np0,enp1s0f1np1)
IB_IF=<ROCE_DEVICES_COMMA_SEPARATED>

# -----------------------------------------------------------------------------
# CONTAINER SETTINGS
# -----------------------------------------------------------------------------
CONTAINER_NAME=vllm_node

# -----------------------------------------------------------------------------
# NCCL TUNING (Required for RDMA performance)
# -----------------------------------------------------------------------------
# Enable InfiniBand/RoCE (0 = enabled, 1 = disabled)
CONTAINER_NCCL_IB_DISABLE=0

# Socket interface for NCCL fallback
CONTAINER_NCCL_SOCKET_IFNAME=<RDMA_INTERFACE>

# RoCE HCA devices for NCCL (same as IB_IF)
CONTAINER_NCCL_IB_HCA=<ROCE_DEVICES_COMMA_SEPARATED>

# Debug level (INFO for troubleshooting, WARN for production)
CONTAINER_NCCL_DEBUG=INFO
```

### Variable Reference

| Variable | Purpose | How to Find Value |
|----------|---------|-------------------|
| `CLUSTER_NODES` | RDMA IPs of all nodes | `ip addr show <RDMA_INTERFACE>` |
| `ETH_IF` | Ethernet interface name | `ip link` (e.g., `enp1s0f1np1`) |
| `IB_IF` | RoCE device names | `ibdev2netdev` (left column) |
| `CONTAINER_NCCL_IB_DISABLE` | Enable RDMA | Always `0` |
| `CONTAINER_NCCL_IB_HCA` | NCCL RoCE devices | Same as `IB_IF` |

### Common Mistake: Interface vs Device Names

```bash
# WRONG - using ethernet interface names
IB_IF=enp1s0f1np1
CONTAINER_NCCL_IB_HCA=enp1s0f1np1

# CORRECT - using RoCE device names
IB_IF=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
CONTAINER_NCCL_IB_HCA=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
```

This mistake causes NCCL to fall back to TCP, resulting in:
- No RDMA traffic visible
- GPU hangs at 100%
- Extremely slow or failing tensor parallelism

See: [NVIDIA Forum Discussion](https://forums.developer.nvidia.com/t/two-spark-cluster-with-vllm-using-tensor-parallel-size-2-causes-one-node-to-drop-while-the-others-gpu-goes-100-forever/358755)

## Single Spark Setup

For running on a single DGX Spark without distributed setup.

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
```

### 2. Build Container

Downloads pre-built wheels and builds the container locally:

```bash
./build-and-copy.sh
```

**Output:**
- Container name: `vllm-node`
- vLLM: `0.20.2rc1` (nightly)
- Transformers: `5.8.0`
- Ray: `2.55.1`

### 3. Download Model

```bash
./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8
```

### 4. Run vLLM Server

**Option A - Using recipe (recommended):**
```bash
./run-recipe.sh qwen3.6-35b-a3b-fp8
```

**Option B - Direct docker run:**
```bash
docker run -d \
  --name vllm_node \
  --gpus all \
  --shm-size=10g \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm-node \
  vllm serve Qwen/Qwen3.6-35B-A3B-FP8 \
    --port 8000 \
    --host 0.0.0.0 \
    --gpu-memory-utilization 0.7 \
    --load-format fastsafetensors
```

**Note about `launch-cluster.sh`:** The repo provides `launch-cluster.sh` which is designed for multi-node setups. For single Spark, use recipes or direct docker commands as shown above.

Container runs as `vllm_node` (note: underscore, not hyphen).

### 5. Verify Server

**Check if model is loaded:**
```bash
curl -s http://localhost:8000/v1/models | jq .
```

**Test inference:**
```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "What is 2+2? Be brief."}],
    "max_tokens": 100
  }'
```

### 6. Benchmark

```bash
docker exec vllm_node vllm bench serve \
  --host localhost \
  --port 8000 \
  --model Qwen/Qwen3.6-35B-A3B-FP8 \
  --random-input-len 2048 \
  --random-output-len 500 \
  --num-prompts 20 \
  --request-rate 5
```

## Benchmark Results

### Qwen3.6-35B-A3B-FP8 (Single DGX Spark)

| Test | Output Len | Throughput | TTFT | TPOT |
|------|------------|------------|------|------|
| Short | 500 | 193 tok/s | 2.96s | 92ms |
| Long | 2000 | **214 tok/s** | 2.53s | 91ms |

**Long output test (2000 tokens):**
```
============ Serving Benchmark Result ============
Successful requests:                     20
Failed requests:                         0
Benchmark duration (s):                  186.87
Total input tokens:                      40960
Total generated tokens:                  40000
--------------------------------------------------
Output token throughput (tok/s):         214.06
Peak output token throughput (tok/s):    240.00
Total token throughput (tok/s):          433.25
--------------------------------------------------
Mean TTFT (ms):                          2531.72
Median TTFT (ms):                        2351.60
P99 TTFT (ms):                           4084.76
--------------------------------------------------
Mean TPOT (ms):                          91.00
Median TPOT (ms):                        91.04
P99 TPOT (ms):                           92.48
==================================================
```

**Key observations:**
- Throughput improves with longer outputs (214 vs 193 tok/s)
- TPOT is very consistent (~91ms) regardless of output length
- TTFT stable at ~2.5s

### Qwen3.6-35B-A3B-FP8 (Dual DGX Spark, TP=2)

**Test:** 50 prompts, 2048 input tokens, 2000 output tokens, 10 req/s

```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  181.76
Total input tokens:                      102400
Total generated tokens:                  100000
--------------------------------------------------
Output token throughput (tok/s):         550.19
Peak output token throughput (tok/s):    650.00
Total token throughput (tok/s):          1113.58
--------------------------------------------------
Mean TTFT (ms):                          4202.14
Median TTFT (ms):                        3994.29
P99 TTFT (ms):                           6850.43
--------------------------------------------------
Mean TPOT (ms):                          87.34
Median TPOT (ms):                        87.47
P99 TPOT (ms):                           89.94
==================================================
```

### Single vs Dual Spark Comparison

| Metric | Single Spark | Dual Spark (TP=2) | Delta |
|--------|--------------|-------------------|-------|
| **Throughput** | 214 tok/s | **550 tok/s** | **+157%** |
| **Peak** | 240 tok/s | **650 tok/s** | **+171%** |
| **TTFT** | **2.53s** | 4.20s | +66% |
| **TPOT** | 91ms | **87ms** | **-4%** |

**Analysis:**
- **Throughput gains**: +157% with dual Spark - proper RDMA enables efficient tensor parallelism
- **TPOT improved**: 87ms on dual vs 91ms on single - cross-node RDMA adds no latency overhead
- **TTFT increase**: Expected due to model being split across nodes
- **Recommendation**:
  - **Interactive use**: Single Spark (lower TTFT)
  - **Batch/throughput**: Dual Spark (2.5x throughput)
  - **Larger models (>128GB)**: Dual Spark required

### Qwen3.6-35B-A3B-FP8 with Speculative Decoding (DFlash)

**Recipe:** `./run-recipe.sh recipes/qwen3.6-35b-a3b-fp8-dflash.yaml`

Uses draft model `z-lab/Qwen3.6-35B-A3B-DFlash` with 5 speculative tokens.

**Test:** 50 prompts, 2048 input tokens, 2000 output tokens, 10 req/s

```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  316.13
Total input tokens:                      102400
Total generated tokens:                  100000
--------------------------------------------------
Output token throughput (tok/s):         316.32
Peak output token throughput (tok/s):    200.00
Total token throughput (tok/s):          640.24
--------------------------------------------------
Mean TTFT (ms):                          42426.61
Mean TPOT (ms):                          93.82
--------------------------------------------------
Acceptance rate (%):                     30.46
Acceptance length:                       2.52
Per-position acceptance (%):
  Position 0: 53.76%
  Position 1: 35.11%
  Position 2: 25.32%
  Position 3: 20.53%
  Position 4: 17.58%
==================================================
```

### Speculative Decoding Comparison

| Metric | Normal | Speculative | Delta |
|--------|--------|-------------|-------|
| **Throughput** | **550 tok/s** | 316 tok/s | -43% |
| **TTFT** | **4.2s** | 42.4s | +910% |
| **TPOT** | **87ms** | 94ms | +8% |
| **Acceptance** | N/A | 30.46% | Too low |

**Why speculative decoding is slower for benchmarks:**
- 30% acceptance rate is insufficient (need >50-60% to benefit)
- Random benchmark tokens are unpredictable
- Draft model initialization adds significant TTFT overhead

**When speculative decoding helps:**
- Code completion (predictable patterns)
- Structured data/JSON generation
- Repetitive text patterns
- Real-world chat (more predictable than random)

**Recommendation:** Use normal dual Spark recipe for benchmarks and general use. Consider speculative for specific predictable workloads.

### Why Random Benchmarks Are Worst-Case for Speculative Decoding

Research confirms that vLLM benchmarks with random prompts represent the worst-case scenario for speculative decoding:

1. **Acceptance rate is critical**: At α ≥ 0.6 and γ ≥ 5, speculative decoding achieves 2-3× speedups. Below that, compute is wasted on drafting and verification. ([Source](https://bentoml.com/llm/inference-optimization/speculative-decoding))

2. **Domain mismatch kills performance**: Generic/random datasets yield lower acceptance rates. Random benchmark tokens are maximally unpredictable. ([Source](https://www.bentoml.com/blog/3x-faster-llm-inference-with-speculative-decoding))

3. **Real user reports**: Similar 30-50% throughput drops reported with speculative decoding when acceptance rates are ~70%. ([vLLM Discussion #13834](https://github.com/vllm-project/vllm/discussions/13834))

4. **Per-position acceptance decay**: Our benchmark showed acceptance dropping from 54% (position 0) to 18% (position 4) - essentially random guessing by the 5th token.

**Real-world workloads where speculative decoding shines:**
- Code completion (highly predictable patterns)
- JSON/structured data generation
- Templated/repetitive text
- Multi-turn chat with context

## Available Recipes

The repo includes pre-configured recipes in `recipes/`:

| Recipe | Model | Quantization |
|--------|-------|--------------|
| `qwen3.6-35b-a3b-fp8` | Qwen3.6-35B-A3B | FP8 |
| `qwen3.6-35b-a3b-fp8-dflash` | Qwen3.6-35B-A3B | FP8 + Speculative |
| `qwen3.5-122b-fp8` | Qwen3.5-122B | FP8 |
| `qwen3.5-397b-int4-autoround` | Qwen3.5-397B | INT4 |
| `minimax-m2-awq` | MiniMax-M2 | AWQ |
| `minimax-m2.5-awq` | MiniMax-M2.5 | AWQ |

## Container Details

- **Container name:** `vllm_node` (underscore)
- **Base image:** CUDA 13.2.0 + Ubuntu 24.04
- **Python:** 3.12

### Key Differences from NGC Setup

| Aspect | NGC Setup | spark-vllm-docker |
|--------|-----------|-------------------|
| Container name | `vllm-spark` | `vllm_node` |
| Launch method | Manual docker run | `./launch-cluster.sh` |
| Ray setup | Manual | Automatic |
| Config | `.env` in playbook | `.env` in repo |

## Stopping

```bash
# Stop the container
docker stop vllm_node && docker rm vllm_node
```

## Dual Spark Setup (Tensor Parallel)

Run models across both DGX Sparks with tensor parallelism over RDMA.

### 1. Build Container on Both Nodes

**Spark 1 (head):**
```bash
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
./build-and-copy.sh
```

**Spark 2 (worker):**
```bash
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
./build-and-copy.sh
```

### 2. Configure Cluster

Create `.env` on Spark 1 (head node) using the template from the [Environment Configuration](#environment-configuration-env) section above.

**Quick setup:**
```bash
cd ~/spark-vllm-docker
cp /path/to/your/env-template .env
# Edit .env with your values
```

**Critical:** Ensure `IB_IF` and `CONTAINER_NCCL_IB_HCA` use RoCE device names (from `ibdev2netdev`), NOT ethernet interface names. See the [Common Mistake](#common-mistake-interface-vs-device-names) section.

### 3. Download Model to Both Nodes

**Option A - Parallel distribution from head:**
```bash
./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8 -c --copy-parallel
```

**Option B - Download on each node separately:**
```bash
# Spark 1
./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8

# Spark 2
ssh <SPARK2_HOST> "cd ~/spark-vllm-docker && ./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8"
```

### 4. Launch Cluster with Tensor Parallelism

From Spark 1 (head node):

**Option A - Using recipe (recommended):**
```bash
./run-recipe.sh recipes/qwen3.6-35b-a3b-fp8.yaml
```

**Option B - Manual launch:**
```bash
./launch-cluster.sh exec vllm serve Qwen/Qwen3.6-35B-A3B-FP8 \
  --port 8000 \
  --host 0.0.0.0 \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --load-format fastsafetensors \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_xml
```

The script automatically:
- Starts containers on both nodes
- Configures Ray cluster over RDMA
- Launches vLLM with tensor parallelism

**Verify RDMA is working:**
You should see multi-gigabit traffic on the RDMA interface during model loading and inference. Use your network monitoring tool or:
```bash
watch -n 1 "cat /sys/class/infiniband/*/ports/*/counters/port_xmit_data"
```

### 5. Verify Cluster

**Check models endpoint:**
```bash
curl -s http://<SPARK1_RDMA_IP>:8000/v1/models | jq .
```

**Test inference:**
```bash
curl -X POST "http://<SPARK1_RDMA_IP>:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

**Verify RDMA traffic during inference:**
```bash
watch -n 1 "cat /sys/class/infiniband/*/ports/*/counters/port_xmit_data"
```

### 6. Benchmark (Dual Spark)

```bash
docker exec vllm_node vllm bench serve \
  --host <SPARK1_RDMA_IP> \
  --port 8000 \
  --model Qwen/Qwen3.6-35B-A3B-FP8 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10
```

### 7. Stop Cluster

```bash
# Stop containers on both nodes
docker stop vllm_node && docker rm vllm_node
ssh <SPARK2_HOST> "docker stop vllm_node && docker rm vllm_node"
```

### Single vs Cluster Comparison

| Aspect | Single Spark | Cluster (Dual+) |
|--------|--------------|-----------------|
| Launch | Recipe or docker run | `./launch-cluster.sh` |
| Nodes | 1 | 2+ |
| Config | Optional | `.env` required |
| TP size | 1 | 2+ |
| Ray | Not used | Automatic setup |
| RDMA | Not needed | Required |

## LiteLLM Proxy for Claude Code

See **[litellm-claude-code.md](litellm-claude-code.md)** for full setup instructions.

**Quick start:**
1. Start vLLM with `--enable-auto-tool-choice --tool-call-parser qwen3_xml`
2. Run LiteLLM on the Spark
3. Set `ANTHROPIC_BASE_URL="http://<SPARK1_HOST>:4000"` on your Mac
4. Run `claude --model claude-3-5-sonnet-20241022`

## Troubleshooting

### RDMA Not Working / No Traffic on RDMA Interface

**Symptoms:**
- Network monitor shows 0 traffic on RDMA interface
- GPU hangs at 100% indefinitely
- Error: "No available shared memory broadcast block found in 60 seconds"
- Very slow tensor parallel performance
- One node drops while the other's GPU stays at 100% forever

**Related issue:** [NVIDIA Developer Forum - Two Spark cluster with vLLM using tensor-parallel-size 2](https://forums.developer.nvidia.com/t/two-spark-cluster-with-vllm-using-tensor-parallel-size-2-causes-one-node-to-drop-while-the-others-gpu-goes-100-forever/358755)

**Cause:** `IB_IF` configured with ethernet interface names instead of RoCE device names, causing NCCL to fall back to TCP instead of RDMA.

**Fix:** Update `.env` with correct RoCE device names:
```bash
# WRONG - ethernet interface name
IB_IF=enp1s0f1np1

# CORRECT - RoCE device names (get from ibdev2netdev)
IB_IF=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1

# Also ensure NCCL settings are correct
CONTAINER_NCCL_IB_DISABLE=0
CONTAINER_NCCL_IB_HCA=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
```

**Verify RDMA is working:**
```bash
# Check NCCL debug output shows IB/RoCE
docker logs vllm_node 2>&1 | grep -i "NCCL.*IB\|NCCL.*RoCE"

# Monitor RDMA traffic (run during inference) - should show multi-gigabit traffic
watch -n 1 "cat /sys/class/infiniband/*/ports/*/counters/port_xmit_data"
```

### Container name confusion
- The script creates `vllm_node` (underscore)
- Not `vllm-node` (hyphen)

### Python not found
Use `python3` not `python`:
```bash
docker exec vllm_node python3 ...
```

### Module not found for benchmark
Use `vllm bench serve` not `python -m vllm.entrypoints.openai.benchmark`:
```bash
docker exec vllm_node vllm bench serve ...
```

### LiteLLM Docker Image Not Found
LiteLLM Docker image doesn't support ARM64 (DGX Spark uses Grace CPU). Use pip:
```bash
pip install 'litellm[proxy]'
litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0
```

## Related Tools

- **[quasar-deck](https://github.com/csabakecskemeti/quasar-deck)** - Cluster monitoring utility for DGX Spark infrastructure
- **[claude-autopilot-sandbox](https://github.com/csabakecskemeti/claude-autopilot-sandbox)** - Claude Code automation sandbox
