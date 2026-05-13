# vLLM Setup with spark-vllm-docker

Set up vLLM inference server on DGX Spark using [spark-vllm-docker](https://github.com/eugr/spark-vllm-docker) - community-maintained builds with latest vLLM for newest model support.

## Placeholder Reference

Replace these placeholders with your values:

| Placeholder | Description | How to Find |
|-------------|-------------|-------------|
| `<SPARK1_HOST>` | Hostname of head node | Your hostname (e.g., `spark1.local`) |
| `<SPARK2_HOST>` | Hostname of worker node | Your hostname (e.g., `spark2.local`) |
| `<SPARK1_RDMA_IP>` | RDMA IP of head node | Run: `ip addr show <RDMA_INTERFACE>` |
| `<SPARK2_RDMA_IP>` | RDMA IP of worker node | Run: `ip addr show <RDMA_INTERFACE>` |
| `<RDMA_INTERFACE>` | Network interface for RDMA | Run: `ip link` (e.g., `enp1s0f1np1`) |
| `<ROCE_DEVICES>` | RoCE device names | Run: `ibdev2netdev` (use left column, comma-separated) |

## Environment Configuration (.env)

The `spark-vllm-docker` repo uses a `.env` file for cluster configuration.

### Complete .env Template

Also available as [.env.example](.env.example).

```bash
# =============================================================================
# spark-vllm-docker Environment Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# CLUSTER NODES
# -----------------------------------------------------------------------------
# Comma-separated RDMA IP addresses (head node FIRST)
# Single Spark: just one IP
# Dual Spark: head,worker
CLUSTER_NODES=<SPARK1_RDMA_IP>,<SPARK2_RDMA_IP>

# -----------------------------------------------------------------------------
# NETWORK INTERFACES
# -----------------------------------------------------------------------------
# Ethernet interface name (find with: ip link)
ETH_IF=<RDMA_INTERFACE>

# RoCE device names - CRITICAL: use device names, NOT interface names!
# Find with: ibdev2netdev (use LEFT column values)
IB_IF=<ROCE_DEVICES_COMMA_SEPARATED>

# -----------------------------------------------------------------------------
# CONTAINER SETTINGS
# -----------------------------------------------------------------------------
CONTAINER_NAME=vllm_node

# -----------------------------------------------------------------------------
# NCCL TUNING (Required for RDMA performance)
# -----------------------------------------------------------------------------
CONTAINER_NCCL_IB_DISABLE=0
CONTAINER_NCCL_SOCKET_IFNAME=<RDMA_INTERFACE>
CONTAINER_NCCL_IB_HCA=<ROCE_DEVICES_COMMA_SEPARATED>
CONTAINER_NCCL_DEBUG=INFO
```

### Common Mistake: Interface vs Device Names

```bash
# WRONG - using ethernet interface names
IB_IF=enp1s0f1np1

# CORRECT - using RoCE device names
IB_IF=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
```

This mistake causes NCCL to fall back to TCP, resulting in GPU hangs and failed tensor parallelism.

See: [NVIDIA Forum Discussion](https://forums.developer.nvidia.com/t/two-spark-cluster-with-vllm-using-tensor-parallel-size-2-causes-one-node-to-drop-while-the-others-gpu-goes-100-forever/358755)

## Single Spark Setup

### 1. Clone Repository

```bash
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
```

### 2. Build Container

```bash
./build-and-copy.sh
```

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

### 5. Verify Server

```bash
curl -s http://localhost:8000/v1/models | jq .
```

### 6. Test Inference

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "What is 2+2? Be brief."}],
    "max_tokens": 100
  }'
```

## Dual Spark Setup (Tensor Parallel)

Run models across both DGX Sparks with tensor parallelism over RDMA.

### 1. Build Container on Both Nodes

```bash
# On each Spark
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
./build-and-copy.sh
```

### 2. Configure Cluster

Create `.env` on Spark 1 (head node) using the template above or copy [.env.example](.env.example).

**Critical:** Use RoCE device names (from `ibdev2netdev`), NOT ethernet interface names.

### 3. Download Model to Both Nodes

```bash
./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8 -c --copy-parallel
```

### 4. Launch Cluster

From Spark 1 (head node):

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

Or use a recipe:
```bash
./run-recipe.sh recipes/qwen3.6-35b-a3b-fp8.yaml
```

### 5. Verify RDMA Traffic

```bash
watch -n 1 "cat /sys/class/infiniband/*/ports/*/counters/port_xmit_data"
```

## Tool Calling for Claude Code

When using vLLM as backend for Claude Code, start with these flags:

```bash
--enable-auto-tool-choice \
--tool-call-parser qwen3_xml
```

Without these flags, Claude Code's tool calls will fail.

## Available Recipes

| Recipe | Model | Quantization |
|--------|-------|--------------|
| `qwen3.6-35b-a3b-fp8` | Qwen3.6-35B-A3B | FP8 |
| `qwen3.6-35b-a3b-fp8-dflash` | Qwen3.6-35B-A3B | FP8 + Speculative |
| `qwen3.5-122b-fp8` | Qwen3.5-122B | FP8 |

## Benchmark Results

### Single vs Dual Spark

| Metric | Single Spark | Dual Spark (TP=2) | Delta |
|--------|--------------|-------------------|-------|
| **Throughput** | 214 tok/s | **550 tok/s** | **+157%** |
| **TTFT** | **2.53s** | 4.20s | +66% |
| **TPOT** | 91ms | **87ms** | -4% |

**Recommendation:**
- **Interactive use**: Single Spark (lower TTFT)
- **High throughput**: Dual Spark (2.5x throughput)
- **Large models (>128GB)**: Dual Spark required

### Run Benchmark

```bash
docker exec vllm_node vllm bench serve \
  --host localhost \
  --port 8000 \
  --model Qwen/Qwen3.6-35B-A3B-FP8 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10
```

## Stopping

```bash
docker stop vllm_node && docker rm vllm_node

# For dual setup, also on worker:
ssh <SPARK2_HOST> "docker stop vllm_node && docker rm vllm_node"
```

## Troubleshooting

### RDMA Not Working

**Symptoms:** GPU hangs at 100%, no RDMA traffic visible

**Fix:** Use RoCE device names in `.env`:
```bash
# Get device names
ibdev2netdev

# Update .env with left column values (roceXXX, not enpXXX)
IB_IF=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
CONTAINER_NCCL_IB_HCA=rocep1s0f0,rocep1s0f1,roceP2p1s0f0,roceP2p1s0f1
```

### Container Name

The script creates `vllm_node` (underscore), not `vllm-node` (hyphen).

### Python Commands

Use `python3` not `python`:
```bash
docker exec vllm_node python3 ...
```

## Next Step

Once vLLM is running, set up [LiteLLM proxy](02-litellm-proxy.md) to use it with Claude Code.
