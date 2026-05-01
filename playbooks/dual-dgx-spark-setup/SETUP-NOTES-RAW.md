# Dual DGX Spark Setup - Raw Notes

> Working notes from setting up two DGX Sparks for distributed inference/training
> Date: 2026-04-26

---

## Goal

Configure two DGX Sparks (both with ConnectX-7) for distributed inference/training over 200Gbps RDMA. Optionally include Linux workstation as third node.

---

## Hardware

| Device | Hostname | GPU | NIC |
|--------|----------|-----|-----|
| Spark 1 | spark-db71 | Grace Blackwell GB10 (128GB) | ConnectX-7 |
| Spark 2 | spark-7ceb | Grace Blackwell GB10 (128GB) | ConnectX-7 |
| Workstation | (optional) | RTX 6000 Pro / RTX 5090 | ConnectX-5 |

---

## Network Topology Decision

### Option Considered
- **Direct QSFP cables** (no switch)
- Spark 1 uses **two ports**: one for workstation, one for Spark 2
- All three devices on **same subnet** (192.168.200.0/24)

### IP Addressing Scheme

Decided on "+10 offset" pattern for easy identification:

| Device | Port A (enp1s0f0np0) | Port B (enp1s0f1np1) | Notes |
|--------|---------------------|---------------------|-------|
| Spark 1 | 192.168.200.1 | 192.168.200.3 | Port A → Workstation, Port B → Spark 2 |
| Spark 2 | 192.168.200.11 | 192.168.200.13 | Port B → Spark 1 |
| Workstation | 192.168.200.2 | - | → Spark 1 Port A |

Rationale: "+10 offset" makes it instantly obvious which Spark an IP belongs to.

---

## Interface Mapping

Both Sparks have identical interface layout:

```
ibdev2netdev output:
rocep1s0f0 port 1 ==> enp1s0f0np0
rocep1s0f1 port 1 ==> enp1s0f1np1
roceP2p1s0f0 port 1 ==> enP2p1s0f0np0
roceP2p1s0f1 port 1 ==> enP2p1s0f1np1
```

Active link for Spark-to-Spark: `enp1s0f1np1` on both devices.

---

## Configuration Steps

### Spark 2 - Fresh Install

#### 1. Install RDMA Packages

```bash
sudo apt update
sudo apt install -y \
  infiniband-diags \
  rdma-core \
  ibverbs-utils \
  mstflint \
  perftest \
  ethtool
```

#### 2. Add User to Docker Group

```bash
sudo usermod -aG docker $USER
newgrp docker
```

#### 3. Install NVIDIA Container Toolkit

> **Note:** Surprisingly, NVIDIA Container Toolkit is NOT pre-installed on DGX Spark. Required for `--runtime=nvidia` in Docker.

```bash
# Add NVIDIA container repo
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify:
```bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.0-base nvidia-smi
```

#### 4. Verify RDMA Stack

```bash
lsmod | grep mlx5
ibv_devinfo
ibdev2netdev
```

#### 5. Configure Netplan

Created `/etc/netplan/99-rdma.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0f0np0:
      addresses:
        - 192.168.200.11/24
      mtu: 9000
      dhcp4: false
    enp1s0f1np1:
      addresses:
        - 192.168.200.13/24
      mtu: 9000
      dhcp4: false
    enP7s7:         # Wired ethernet - primary internet
      dhcp4: true
```

```bash
sudo chmod 600 /etc/netplan/99-rdma.yaml
sudo netplan apply
```

### Spark 1 - Existing Config Updated

`/etc/netplan/99-rdma.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0f0np0:
      addresses:
        - 192.168.200.1/24
      mtu: 9000
      dhcp4: false
    enp1s0f1np1:
      addresses:
        - 192.168.200.3/24
      mtu: 9000
      dhcp4: false
    enP7s7:         # Wired ethernet - primary internet
      dhcp4: true
```

---

## Issues Encountered

### Issue 1: netplan apply Hanging

**Symptom:** `sudo netplan apply` hangs indefinitely.

**Cause:** DHCP timeout on `enP7s7` interface (waiting for IP from DHCP server).

**Solution:** Either:
1. Ensure ethernet cable is connected to enP7s7, or
2. Add `optional: true` to the interface config:
   ```yaml
   enP7s7:
     dhcp4: true
     optional: true
   ```

### Issue 2: mDNS Hostname Conflict

**Symptom:** `ping spark-7ceb.local` times out, but `ping <IP>` works.

**Diagnosis:** Checked Avahi status:
```bash
sudo systemctl status avahi-daemon
```
Output showed: `avahi-daemon: running [spark-7ceb-2.local]`

**Cause:** Avahi detected hostname conflict on network, auto-appended `-2` suffix.

**Solution:** Restart Avahi daemon:
```bash
sudo systemctl restart avahi-daemon
```

Hostname resolved correctly after restart.

---

## Performance Testing

### RDMA Bandwidth Tests

Using `ib_send_bw` between Spark 1 and Spark 2.

#### Test 1: Single Queue Pair (Unidirectional)

```bash
# Spark 1 (server)
ib_send_bw -d rocep1s0f1

# Spark 2 (client)
ib_send_bw -d rocep1s0f1 192.168.200.3
```

**Result:**
```
#bytes     #iterations    BW peak[MB/sec]    BW average[MB/sec]   MsgRate[Mpps]
65536      1000             12977.55            12976.86           0.207630
```
~104 Gbps unidirectional

#### Test 2: Multiple Queue Pairs (-q 4)

```bash
ib_send_bw -d rocep1s0f1 -q 4
ib_send_bw -d rocep1s0f1 -q 4 192.168.200.3
```

**Result:**
```
#bytes     #iterations    BW peak[MB/sec]    BW average[MB/sec]   MsgRate[Mpps]
65536      4000             13297.84            13297.09           0.212753
```
~106 Gbps - no significant improvement

#### Test 3: Bidirectional (-b)

```bash
# Spark 1 (server)
ib_send_bw -d rocep1s0f1 -b

# Spark 2 (client)
ib_send_bw -d rocep1s0f1 -b 192.168.200.3
```

**Result:**
```
#bytes     #iterations    BW peak[MB/sec]    BW average[MB/sec]   MsgRate[Mpps]
65536      1000             25494.85            25490.52           0.407848
```
**~204 Gbps bidirectional** - Full 200G link utilized!

---

## Hardware Analysis

### Link Speed Verification

```bash
ethtool enp1s0f1np1 | grep -i speed
```

Output: `Speed: 200000Mb/s` - Confirmed 200Gbps link.

### PCIe Configuration

```bash
sudo lspci -vvv | grep -A 20 -i mellanox | grep -E "LnkCap|LnkSta|Width"
```

Output:
```
LnkCap:    Port #0, Speed 32GT/s, Width x4, ASPM not supported
LnkSta:    Speed 32GT/s, Width x4
```

### ibstat Rate

```bash
ibstat | grep -i rate
```

Output:
```
Rate: 40    # unused ports
Rate: 200   # active ports
Rate: 40
Rate: 200
```

### Key Finding: PCIe x4 Bottleneck (Validated)

| Component | Specification | Bandwidth |
|-----------|--------------|-----------|
| Network Link | 200 Gbps | 200 Gbps |
| PCIe Gen5 x4 | 32GT/s × 4 lanes | ~126 Gbps theoretical, ~100 Gbps practical |

**Conclusion:** PCIe x4 limits unidirectional throughput to ~100 Gbps. However, for bidirectional workloads (like NCCL all-reduce), full ~200 Gbps aggregate is achieved since PCIe can handle ~100G in each direction simultaneously.

**Impact on distributed training:** Minimal. NCCL operations are bidirectional, so full 200G benefit is realized.

#### External Validation (ServeTheHome Review)

This is confirmed by ServeTheHome's DGX Spark review:
- "a Gen5 x4 link is roughly a 100Gbps NIC"
- Single port iperf3 test: ~96 Gbps
- Dual port combined iperf3 test: still ~96 Gbps (PCIe bottleneck, not additive)
- The ConnectX-7 itself is 200GbE capable, but PCIe x4 is the limiting factor

**Source:** [ServeTheHome DGX Spark Review](https://www.servethehome.com/nvidia-dgx-spark-review-the-gb10-machine-is-so-freaking-cool/2/)

Our bidirectional RDMA test achieving ~204 Gbps represents optimal performance for this hardware configuration.

---

## SSH Configuration

### Generate Keys (if needed)

Spark 2 required key generation (fresh install):
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

### Passwordless SSH Setup

On Spark 1:
```bash
ssh-copy-id kecso@spark2-rdma
```

On Spark 2:
```bash
ssh-copy-id kecso@spark1-rdma
```

### Verification

```bash
# From Spark 1
ssh kecso@spark2-rdma hostname
# Expected: spark-7ceb

# From Spark 2
ssh kecso@spark1-rdma hostname
# Expected: spark-db71
```

---

## Network Topology Notes

### Workstation Connectivity from Spark 2

Currently Spark 2 is **not directly connected to the workstation**. Options for future:

1. **Use Spark 2's second port** - but it's currently occupied by the Spark-to-Spark link
2. **Route via Spark 1** - would require IP forwarding/routing setup on Spark 1
3. **Add a switch** - cleanest solution, all three nodes on same network segment

For now, workstation entry is commented out in Spark 2's `/etc/hosts`:
```
# 192.168.200.2   workstation
```

---

## NCCL Communication Test

### Test Script (test_nccl.py)

Updated for Spark-to-Spark configuration:
- `MASTER_ADDR`: `192.168.200.3` (Spark 1 interconnect IP)
- `NCCL_SOCKET_IFNAME`: `enp1s0f1np1` (interconnect interface)

```python
import os
import torch
import torch.distributed as dist
import argparse

def test_nccl_communication():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, required=True)
    parser.add_argument('--world_size', type=int, default=2)
    parser.add_argument('--master_addr', type=str, default='192.168.200.3')
    parser.add_argument('--master_port', type=str, default='29501')
    args = parser.parse_args()

    os.environ['RANK'] = str(args.rank)
    os.environ['WORLD_SIZE'] = str(args.world_size)
    os.environ['MASTER_ADDR'] = args.master_addr
    os.environ['MASTER_PORT'] = args.master_port
    os.environ['NCCL_SOCKET_IFNAME'] = 'enp1s0f1np1'

    print(f"Initializing process group - Rank: {args.rank}, World Size: {args.world_size}")
    print(f"Master: {args.master_addr}:{args.master_port}")

    dist.init_process_group(backend='nccl', rank=args.rank, world_size=args.world_size)
    print(f"Process group initialized - Rank: {dist.get_rank()}/{dist.get_world_size()}")

    device = torch.device('cuda:0')
    tensor = torch.ones(10, device=device) * (args.rank + 1)
    print(f"Rank {args.rank} - Before allreduce: {tensor}")

    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    print(f"Rank {args.rank} - After allreduce: {tensor}")
    print(f"Expected result: {torch.ones(10) * (1 + 2)}")

    dist.destroy_process_group()
    print(f"Rank {args.rank} - Test completed successfully!")

if __name__ == "__main__":
    test_nccl_communication()
```

### Docker Commands

**Spark 1 (rank 0) - start first:**
```bash
docker run -it --runtime=nvidia --gpus all --network host --ipc=host \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 -v $(pwd):/workspace \
  nvcr.io/nvidia/vllm:26.03-py3 python /workspace/test_nccl.py --rank 0
```

**Spark 2 (rank 1):**
```bash
docker run -it --runtime=nvidia --gpus all --network host --ipc=host \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 -v $(pwd):/workspace \
  nvcr.io/nvidia/vllm:26.03-py3 python /workspace/test_nccl.py --rank 1
```

### Test Result

```
Master: 192.168.200.3:29501
Process group initialized - Rank: 0/2
Rank 0 - Before allreduce: tensor([1., 1., 1., 1., 1., 1., 1., 1., 1., 1.], device='cuda:0')
Rank 0 - After allreduce: tensor([3., 3., 3., 3., 3., 3., 3., 3., 3., 3.], device='cuda:0')
Expected result: tensor([3., 3., 3., 3., 3., 3., 3., 3., 3., 3.])
Rank 0 - Test completed successfully!
```

**Success!** All-reduce operation completed correctly over 200G RDMA link.

### Troubleshooting Notes

- **Port 29500 in use:** Use `--master_port 29501` or kill existing process with `sudo fuser -k 29500/tcp`
- Used port 29501 for this test

---

## Distributed Inference Setup

### vLLM Container Version

**Recommended:** `nvcr.io/nvidia/vllm:26.03-py3` (April 2026, vLLM 0.17.1)

> **IMPORTANT:** The 26.02 container has bugs with NVFP4 on Blackwell SM121 (illegal instruction errors during CUDA graph capture). Use **26.03** for NVFP4 support.

| Container | vLLM Version | NVFP4 Support | Notes |
|-----------|--------------|---------------|-------|
| 26.02-py3 | 0.15.1 | ❌ Broken | Illegal instruction errors |
| **26.03-py3** | **0.17.1** | **✅ Works** | Verified on dual DGX Spark TP=2 |

**Pull the recommended container:**
```bash
docker pull nvcr.io/nvidia/vllm:26.03-py3
```

> **Note:** The 26.03 container may still require `pip install --upgrade transformers` for newer model architectures like Qwen3.5 MoE.

> **DGX Spark tip:** On unified memory systems, use `--gpu-memory-utilization 0.7` to avoid OOM.

### Start RDMA-Enabled Containers

**Spark 1 (head node):**
```bash
docker run -it --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband \
  -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  -e NCCL_IB_DISABLE=0 \
  -e NCCL_IB_HCA=rocep1s0f1:1 \
  -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=192.168.200.3 \
  -e RAY_OVERRIDE_NODE_IP=192.168.200.3 \
  -e VLLM_HOST_IP=192.168.200.3 \
  nvcr.io/nvidia/vllm:26.03-py3 bash
```

**Spark 2 (worker node):**
```bash
docker run -it --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband \
  -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  -e NCCL_IB_DISABLE=0 \
  -e NCCL_IB_HCA=rocep1s0f1:1 \
  -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=192.168.200.13 \
  -e RAY_OVERRIDE_NODE_IP=192.168.200.13 \
  nvcr.io/nvidia/vllm:26.03-py3 bash
```

### Start Ray Cluster

**Inside Spark 1 container (head):**
```bash
ray start --head \
  --node-ip-address=192.168.200.3 \
  --port=6379 \
  --dashboard-host=192.168.200.3 \
  --dashboard-port=8265 \
  --num-gpus=1
```

**Inside Spark 2 container (worker):**
```bash
ray start \
  --address=192.168.200.3:6379 \
  --node-ip-address=192.168.200.13 \
  --num-gpus=1
```

Verify with `ray status` - should show 2 GPUs total.

### Run Distributed Inference (Qwen3-4B)

**Inside Spark 1 container:**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-4B-Instruct-2507 \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.8 \
  --host 0.0.0.0 \
  --port 8000
```

> **Note:** Using `--host 0.0.0.0` allows calling the API from any network interface (e.g., from Mac via `spark-db71.local`), while GPU-to-GPU communication still uses RDMA over `192.168.200.x`.

### Test API

From Mac or any machine on the network:
```bash
curl -X POST "http://spark-db71.local:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B-Instruct-2507",
    "messages": [
      {"role": "user", "content": "What is RDMA and why is it useful for AI?"}
    ],
    "max_tokens": 200
  }'
```

---

## Model Testing

### Models Tested

| Model | Quantization | Size | Status | Notes |
|-------|-------------|------|--------|-------|
| Qwen/Qwen3-4B-Instruct-2507 | BF16 | ~8GB | ✅ Works | Validation test |
| Qwen/Qwen3-235B-A22B-FP8 | FP8 | ~235GB | ❌ OOM | Too large for 256GB combined |
| Qwen/Qwen3-235B-A22B-GPTQ-Int4 | GPTQ Int4 | ~60GB | ✅ Works | **149 tok/s** - Best performance |
| QuixiAI/Qwen3-235B-A22B-AWQ | AWQ | ~60GB | ✅ Works | 141 tok/s - Close second |
| nvidia/Qwen3.5-397B-A17B-NVFP4 | NVFP4 | ~50GB | ❌ Not supported | vLLM 0.15.1 doesn't support Qwen3.5 |
| nvidia/Qwen3-235B-A22B-NVFP4 | NVFP4 | ~62GB/node | ⚠️ Unstable | 84 tok/s (eager), crashes during shutdown |
| MrVolts/Qwen3-30B-A3B-NVFP4 | NVFP4 | ~10GB | ❌ Broken | Compiled: 70 tok/s (crashes), Eager: 12 tok/s (24% failures) |

### Model Compatibility Notes

**vLLM 0.15.1 (in 26.02 container) supports:**
- `Qwen2ForCausalLM`, `Qwen2MoeForCausalLM`
- `Qwen3ForCausalLM`, `Qwen3MoeForCausalLM`
- Does NOT support: `Qwen3_5MoeForConditionalGeneration` (requires newer transformers)

**Fix for Qwen3.5 models:**
```bash
pip install --upgrade transformers
```

### Quantization Options for DGX Spark

| Format | Memory Savings | Blackwell Native | Notes |
|--------|---------------|------------------|-------|
| BF16 | 1× (baseline) | Yes | Full precision |
| FP8 | ~2× | Yes | Good balance |
| GPTQ Int4 | ~4× | No | Software dequant |
| AWQ Int4 | ~4× | No | Software dequant |
| **NVFP4** | ~4× | **Yes** | Native FP4 tensor cores, best for Blackwell |

### NVFP4 Models (Recommended for DGX Spark)

NVFP4 uses native Blackwell FP4 tensor cores for hardware-accelerated inference.

Available models:
- `nvidia/Qwen3.5-397B-A17B-NVFP4` (~50GB) - Flagship MoE
- `nvidia/Gemma-4-31B-IT-NVFP4` (~10GB) - Google's latest
- `nvidia/Llama-3.3-70B-NVFP4` (~18GB) - Meta 70B
- `nvidia/DeepSeek-R1-NVFP4` - Reasoning model

### Memory Estimates for 256GB Combined

| Model Size | BF16 | FP8 | GPTQ/AWQ Int4 | NVFP4 |
|------------|------|-----|---------------|-------|
| 70B | 140GB | 70GB | 35GB | 35GB |
| 235B MoE | 470GB | 235GB | ~60GB | ~60GB |
| 397B MoE | 794GB | 397GB | ~100GB | ~50GB |

**Recommendation:** For 256GB combined, target models <150GB after quantization, leaving room for KV cache.

---

## NVFP4 Testing Notes

### Why NVFP4 vs GPTQ?

| Aspect | GPTQ-Int4 | NVFP4 |
|--------|-----------|-------|
| Tensor cores | No (software dequant) | **Yes** (native Blackwell FP4) |
| torch.compile | Not needed (eager mode) | Required for performance |
| JIT compilation | None | Flashinfer CUTLASS kernels |
| Memory during load | Model only (~60GB) | Model + compile overhead (~100GB+) |

NVFP4 should be faster at inference due to native FP4 tensor cores, but requires JIT compilation which is memory-intensive.

### Issue 1: Ray OOM During torch.compile

When loading `nvidia/Qwen3-235B-A22B-NVFP4`, the model weights load successfully (~62.54 GiB per node), but Ray kills the worker during `torch.compile` phase.

**Root cause:** CUDA compiler (`cicc`) processes consume ~5-6GB each during torch.compile. Multiple parallel compilations push system RAM past Ray's 95% threshold.

```
Memory on node: 115.76GB / 121.69GB (95.1%)

Top memory users during compile:
5035    6.07GB    cicc (CUDA compiler)
5033    6.03GB    cicc
5044    5.92GB    cicc
...
```

**Attempted fix 1:** `RAY_memory_usage_threshold=0.99`
- Result: **Failed** - env var must be set before `ray start`, not just for vllm
- Error still showed 0.95 threshold

**Attempted fix 2:** Set env var before Ray start on both nodes
```bash
ray stop
export RAY_memory_usage_threshold=0.99
ray start --head ...
```
- Result: **Failed** - Spark 2 still killed at 95.1% threshold
- Env var didn't propagate correctly to worker node

**Attempted fix 3:** `RAY_memory_monitor_refresh_ms=0` (disable monitor)
```bash
ray stop
export RAY_memory_monitor_refresh_ms=0
ray start --head ...
```
- Result: **Passed Ray check** - but hit Issue 2 below

### Issue 2: Flashinfer JIT Compilation OOM

After disabling Ray's memory monitor, torch.compile succeeded but flashinfer's JIT compilation of CUTLASS MoE kernels failed.

```
RuntimeError: Ninja build failed.
FAILED: [code=137] .../cutlass_kernel_file_gemm_grouped_sm120_M128_BS_group0.generated.cuda.o
Killed
ninja: build stopped: subcommand failed.
```

**Root cause:** Exit code 137 = Linux OOM killer (SIGKILL). Flashinfer compiles 24 CUDA files with `-j 12` parallelism. Each nvcc process uses 4-6GB RAM for CUTLASS SM120 (Blackwell) kernels.

Math: 62GB model + 12 × 5GB compile = ~122GB > 128GB per node

### Potential Solutions

**Option 1: Reduce ninja parallelism**
```bash
export MAX_JOBS=2
export NINJA_MAX_JOBS=2
```
Slower compilation but fits in memory.

**Option 2: Pre-compile on single node**
Run on single Spark first to cache kernels:
```bash
python -m vllm.entrypoints.openai.api_server \
  --model nvidia/Qwen3-235B-A22B-NVFP4 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.5 \
  --max-model-len 1024 \
  --enforce-eager
```
Will fail for inference but caches kernels in `~/.cache/flashinfer/`.

**Option 3: Share cache between nodes**
After compiling on one node:
```bash
rsync -av ~/.cache/flashinfer/ spark2-rdma:~/.cache/flashinfer/
rsync -av ~/.cache/vllm/ spark2-rdma:~/.cache/vllm/
```

**Option 4: Use --enforce-eager (current test)**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model nvidia/Qwen3-235B-A22B-NVFP4 \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 32768 \
  --enforce-eager
```
Skips torch.compile and CUDA graphs. Slower but avoids compilation OOM.

### Current Status

- [x] Test with RAY_memory_usage_threshold=0.99 - **Failed** (env var propagation issue)
- [x] Test with RAY_memory_monitor_refresh_ms=0 - **Passed Ray**, failed flashinfer JIT
- [x] Test with --enforce-eager - **Works!**
- [x] Benchmark NVFP4 (eager) vs GPTQ-Int4 - **GPTQ wins** (see below)
- [x] **Fix found: Use vLLM 26.03 container** - Fixes illegal instruction errors on SM121

### Container Version Fix

The 26.02 container has bugs with NVFP4 on Blackwell:
- `cudaErrorIllegalInstruction` during CUDA graph capture
- Affects both 235B and 30B NVFP4 models

**Solution:** Upgrade to `nvcr.io/nvidia/vllm:26.03-py3`

```bash
docker pull nvcr.io/nvidia/vllm:26.03-py3
```

With 26.03:
- NVFP4 models compile successfully
- CUDA graphs capture without errors
- Full torch.compile optimizations work
- **However:** Still crashes at end of benchmark with `cudaErrorIllegalInstruction`
- Performance is disappointing (see benchmarks below)

### NVFP4 Compiled Benchmark (26.03 Container)

**Test Configuration:**
- Model: `MrVolts/Qwen3-30B-A3B-Thinking-2507-NVFP4`
- Container: `nvcr.io/nvidia/vllm:26.03-py3`
- Mode: Compiled (torch.compile + CUDA graphs)
- Hardware: 2× DGX Spark (256GB combined)
- Tensor Parallel Size: 2

**Benchmark Results:**
```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Total generated tokens:                  9,637
--------------------------------------------------
Output token throughput (tok/s):         70.07
--------------------------------------------------
Mean TTFT (ms):                          7,352
--------------------------------------------------
Mean TPOT (ms):                          662.54
==================================================
```

**Analysis:**
- 70 tok/s for a 30B model is **poor performance**
- For comparison, 235B GPTQ achieves 149 tok/s (2× faster with 8× more parameters!)
- TTFT of 7.3s is acceptable
- TPOT of 662ms (~1.5 tok/s per request) is slow
- Engine crashed with `cudaErrorIllegalInstruction` after benchmark completed
- **Verdict:** NVFP4 on Blackwell still not production-ready even with 26.03

**Crash Details:**
```
E NCCL WARN Cuda failure 'an illegal instruction was encountered'
vllm.engine.multiprocessing.client:ENGINE_DEAD
```
The crash occurred during NCCL watchdog, suggesting issues with multi-node NVFP4 communication.

### NVFP4 Benchmark Results (enforce-eager mode)

**Test Configuration:**
- Model: `nvidia/Qwen3-235B-A22B-NVFP4`
- Mode: `--enforce-eager` (no torch.compile, no CUDA graphs)
- Hardware: 2× DGX Spark (256GB combined unified memory)
- Interconnect: 200Gbps RDMA
- Tensor Parallel Size: 2

**Benchmark Command:**
```bash
vllm bench serve \
  --host 192.168.200.3 \
  --port 8000 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10 \
  --model nvidia/Qwen3-235B-A22B-NVFP4
```

**Results:**
```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  293.50
Total input tokens:                      102,400
Total generated tokens:                  24,737
--------------------------------------------------
Output token throughput (tok/s):         84.28
Peak output token throughput (tok/s):    200.00
Total token throughput (tok/s):          433.17
--------------------------------------------------
Mean TTFT (ms):                          24,171
Median TTFT (ms):                        23,794
P99 TTFT (ms):                           45,054
--------------------------------------------------
Mean TPOT (ms):                          334.33
Median TPOT (ms):                        328.81
P99 TPOT (ms):                           521.67
==================================================
```

### Performance Comparison: GPTQ-Int4 vs NVFP4 (eager)

| Metric | GPTQ-Int4 | NVFP4 (eager) | Winner |
|--------|-----------|---------------|--------|
| Output throughput | **149.05 tok/s** | 84.28 tok/s | GPTQ (+77%) |
| Mean TTFT | 26,978 ms | **24,171 ms** | NVFP4 (-10%) |
| Mean TPOT | **318.73 ms** | 334.33 ms | GPTQ (-5%) |
| P99 TPOT | **330.29 ms** | 521.67 ms | GPTQ (-37%) |

**Analysis:**
- **GPTQ-Int4 is significantly faster** in eager mode (~77% higher throughput)
- NVFP4 has slightly better TTFT (first token latency)
- GPTQ has better TPOT consistency (lower P99)
- Without torch.compile + CUDA graphs, NVFP4 loses its native tensor core advantage

**Conclusion:**
For DGX Spark with limited memory, **GPTQ-Int4 is the practical choice** until:
1. Pre-compilation workflow is established for NVFP4
2. Or vLLM/flashinfer ships pre-compiled Blackwell kernels
3. Or memory overhead is reduced in future versions

The native FP4 tensor cores alone don't compensate for the lack of compiled optimizations. GPTQ's pre-compiled Marlin kernels are highly optimized and win in eager mode.

### NVFP4 Status Summary (April 2026)

| Test | Container | Mode | Result | Performance |
|------|-----------|------|--------|-------------|
| 235B NVFP4 | 26.02 | Compiled | ❌ OOM during JIT | - |
| 235B NVFP4 | 26.02 | Eager | ✅ Works | 84 tok/s |
| 30B NVFP4 | 26.02 | Compiled | ❌ Illegal instruction | - |
| 30B NVFP4 | 26.03 | Compiled | ⚠️ Runs but crashes at end | 70 tok/s |
| 30B NVFP4 | 26.03 | Eager | ❌ Broken | 12 tok/s, 24% failed |
| 235B GPTQ | 26.03 | Eager (Marlin) | ✅ Stable | **149 tok/s** |

### 30B NVFP4 Eager Mode Benchmark (26.03 Container)

**Test Configuration:**
- Model: `MrVolts/Qwen3-30B-A3B-Thinking-2507-NVFP4`
- Container: `nvcr.io/nvidia/vllm:26.03-py3`
- Mode: `--enforce-eager` (no torch.compile, no CUDA graphs)
- Hardware: 2× DGX Spark (256GB combined)
- Tensor Parallel Size: 2

**Benchmark Results:**
```
============ Serving Benchmark Result ============
Successful requests:                     38
Failed requests:                         12
Total generated tokens:                  119
--------------------------------------------------
Output token throughput (tok/s):         12.29
--------------------------------------------------
Mean TTFT (ms):                          2,352
Mean TPOT (ms):                          2,300
==================================================
```

**Analysis:**
- **Catastrophically broken** - only 119 tokens generated total
- 24% request failure rate ("Never received a valid chunk")
- 12 tok/s throughput is unusable
- Eager mode is **worse** than compiled mode (70 tok/s)
- Neither mode is production-ready

**Key Finding:** NVFP4 on multi-node DGX Spark is fundamentally broken in vLLM 26.03:
- Compiled mode: 70 tok/s, crashes at end
- Eager mode: 12 tok/s, 24% failures, barely generates tokens
- Both modes are far below expected performance for a 30B model

**Recommendation:** Use **GPTQ-Int4** for stable, high-performance inference on dual DGX Spark. NVFP4 needs significant vLLM/flashinfer work before it's viable on Blackwell multi-node setups. The software stack is simply not ready.

### AWQ Benchmark Results

**Test Configuration:**
- Model: `QuixiAI/Qwen3-235B-A22B-AWQ`
- Hardware: 2× DGX Spark (256GB combined unified memory)
- Interconnect: 200Gbps RDMA
- Tensor Parallel Size: 2

**Benchmark Command:**
```bash
vllm bench serve \
  --host 192.168.200.3 \
  --port 8000 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10 \
  --model QuixiAI/Qwen3-235B-A22B-AWQ
```

**Results:**
```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  706.96
Total input tokens:                      102,400
Total generated tokens:                  100,000
--------------------------------------------------
Output token throughput (tok/s):         141.45
Peak output token throughput (tok/s):    200.00
Total token throughput (tok/s):          286.30
--------------------------------------------------
Mean TTFT (ms):                          35,786
Median TTFT (ms):                        33,377
P99 TTFT (ms):                           73,950
--------------------------------------------------
Mean TPOT (ms):                          332.05
Median TPOT (ms):                        333.39
P99 TPOT (ms):                           345.97
==================================================
```

### Full Quantization Comparison (Qwen3-235B-A22B)

| Metric | GPTQ-Int4 | AWQ | NVFP4 (eager) |
|--------|-----------|-----|---------------|
| **Output throughput** | **149.05 tok/s** | 141.45 tok/s | 84.28 tok/s |
| Mean TTFT | **26,978 ms** | 35,786 ms | 24,171 ms |
| Mean TPOT | **318.73 ms** | 332.05 ms | 334.33 ms |
| P99 TPOT | **330.29 ms** | 345.97 ms | 521.67 ms |
| Compiled mode | Eager (Marlin) | Eager (Marlin) | Eager (no compile) |

**Rankings:**
1. **GPTQ-Int4** - Best overall throughput (149 tok/s), best latency
2. **AWQ** - Close second (141 tok/s, ~5% slower), may have quality advantages
3. **NVFP4 (eager)** - Slowest without compilation (84 tok/s, ~44% slower)

**Recommendation:** Use **GPTQ-Int4** for maximum throughput on DGX Spark dual-node setup.

---

## Performance Benchmarks

### Qwen3-235B-A22B-GPTQ-Int4 (Dual Spark, Tensor Parallel)

**Test Configuration:**
- Model: `Qwen/Qwen3-235B-A22B-GPTQ-Int4`
- Hardware: 2× DGX Spark (256GB combined unified memory)
- Interconnect: 200Gbps RDMA (bidirectional)
- Tensor Parallel Size: 2
- GPU Memory Utilization: 0.7

**Benchmark Command:**
```bash
vllm bench serve \
  --host 192.168.200.3 \
  --port 8000 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10 \
  --model Qwen/Qwen3-235B-A22B-GPTQ-Int4
```

**Results:**
```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  670.94
Total input tokens:                      102,400
Total generated tokens:                  100,000
--------------------------------------------------
Output token throughput (tok/s):         149.05
Peak output token throughput (tok/s):    200.00
Total token throughput (tok/s):          301.67
--------------------------------------------------
Mean TTFT (ms):                          26,978
Median TTFT (ms):                        23,578
P99 TTFT (ms):                           61,828
--------------------------------------------------
Mean TPOT (ms):                          318.73
Median TPOT (ms):                        320.42
P99 TPOT (ms):                           330.29
==================================================
```

**Analysis:**
- **149 tok/s** output throughput for a 235B MoE model over distributed inference
- **0 failed requests** - stable operation
- **TTFT ~27s** - expected for 2048 input tokens on 235B model
- **TPOT ~319ms** - ~3.14 tokens/sec per request
- Peak concurrent: 50 requests handled successfully

**Key Achievement:** Running a 235B parameter MoE model distributed across two DGX Sparks connected via 200Gbps RDMA, with stable throughput of ~150 tok/s.

---

## TODO / Next Steps

- [x] Configure SSH passwordless access between Sparks
- [x] Configure /etc/hosts with hostnames
- [x] Test NCCL communication in Docker containers
- [x] Set up Ray cluster across both Sparks
- [x] Run distributed inference validation (Qwen3-4B)
- [x] Test larger model (Qwen3-235B-A22B-GPTQ-Int4)
- [x] Benchmark GPTQ-Int4: 149 tok/s output throughput
- [x] Test NVFP4 model with --enforce-eager - **Works!**
- [x] Benchmark NVFP4 vs GPTQ-Int4 - **GPTQ wins** (149 vs 84 tok/s)
- [x] Benchmark AWQ - 141 tok/s (close to GPTQ)
- [ ] Try NVFP4 pre-compilation approach
- [ ] Benchmark: single Spark vs dual Spark performance
- [ ] Document three-node setup (2 Sparks + Workstation) - requires switch or routing

---

## Commands Reference

### Quick Diagnostics

```bash
# Check RDMA interfaces
ibdev2netdev

# Check link speed
ethtool enp1s0f1np1 | grep -i speed

# Check PCIe
sudo lspci -vvv | grep -A 20 -i mellanox | grep -E "LnkCap|LnkSta"

# Check RDMA device info
ibv_devinfo

# Test connectivity
ping 192.168.200.3   # from Spark 2
ping 192.168.200.13  # from Spark 1
```

### Bandwidth Tests

```bash
# Server (Spark 1)
ib_send_bw -d rocep1s0f1 -b

# Client (Spark 2)
ib_send_bw -d rocep1s0f1 -b 192.168.200.3
```

---

## Research Findings

### NVFP4 Pre-compilation Options

The goal is to pre-compile flashinfer CUTLASS kernels before loading the 62GB model weights, avoiding the OOM during JIT compilation.

#### Option 1: Reduce Compilation Parallelism

```bash
# Reduce ninja parallelism from 12 to 2
export MAX_JOBS=2
export NINJA_MAX_JOBS=2

# Or single-threaded (slowest but safest):
export MAX_JOBS=1
export NINJA_MAX_JOBS=1
```

This reduces peak memory from ~60GB (12 × 5GB) to ~10GB (2 × 5GB), which should fit alongside the 62GB model.

#### Option 2: Share Pre-compiled Cache Between Nodes

Flashinfer caches compiled kernels at:
```
~/.cache/flashinfer/
~/.cache/vllm/torch_compile_cache/
```

**Workflow:**
1. Compile on Spark 1 first (single node, reduced parallelism)
2. Copy cache to Spark 2
3. Run distributed inference with cached kernels

```bash
# After successful compilation on Spark 1:
rsync -av ~/.cache/flashinfer/ spark2-rdma:~/.cache/flashinfer/
rsync -av ~/.cache/vllm/ spark2-rdma:~/.cache/vllm/
```

#### Option 3: Pipeline Parallel vs Tensor Parallel

| Mode | Layer Distribution | Compilation Scope |
|------|-------------------|-------------------|
| Tensor Parallel | ALL layers on each node (split horizontally) | Compiles ALL kernel variants |
| Pipeline Parallel | DIFFERENT layers on each node | May compile only needed kernels |

**Hypothesis:** Pipeline parallel (`--pipeline-parallel-size 2`) might reduce per-node compilation because each node only handles half the layers.

**Test command:**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model nvidia/Qwen3-235B-A22B-NVFP4 \
  --pipeline-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --host 0.0.0.0 \
  --port 8000
```

**Note:** Pipeline parallel has different performance characteristics (more network hops per token) but might solve the compilation OOM.

#### Option 4: Pre-warm on High-RAM Workstation

If compilation can run on CPU (unlikely for CUDA kernels), the 1TB RAM workstation could be used:
1. Install matching CUDA toolkit and flashinfer
2. Trigger compilation
3. Copy cache to DGX Sparks

**Reality check:** CUDA kernel compilation requires nvcc and GPU architecture flags, so this likely won't work for GPU kernels. But worth investigating if there's a CPU-only compilation path.

#### Option 5: Staged Compilation Script

```python
# pre_compile_nvfp4.py - Run BEFORE loading full model
import os
os.environ['MAX_JOBS'] = '2'
os.environ['NINJA_MAX_JOBS'] = '2'

# Import flashinfer to trigger kernel compilation
import flashinfer
from flashinfer.fused_moe.core import gen_cutlass_fused_moe_sm120_module

print("Pre-compiling flashinfer CUTLASS MoE kernels for SM120...")
try:
    module = gen_cutlass_fused_moe_sm120_module(use_fast_build=False)
    module.build_and_load()
    print("SUCCESS: Kernels compiled and cached!")
except Exception as e:
    print(f"Compilation failed: {e}")
```

Run this on each node before starting vLLM with the NVFP4 model.

---

### LiteLLM Proxy for Claude Code

Claude Code requires Anthropic Messages API format, but vLLM only exposes OpenAI Chat Completions API. LiteLLM acts as a translation proxy.

#### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Claude Code │────▶│   LiteLLM   │────▶│    vLLM     │
│  (Client)   │     │   (Proxy)   │     │  (Server)   │
└─────────────┘     └─────────────┘     └─────────────┘
   Anthropic          Translation         OpenAI
   Messages API                           Chat API
```

#### Installation

```bash
pip install 'litellm[proxy]'
```

#### Configuration File

Create `litellm_config.yaml`:

```yaml
model_list:
  # Map Claude model names to local vLLM
  - model_name: claude-3-opus-20240229
    litellm_params:
      model: openai/Qwen3-235B-A22B-GPTQ-Int4
      api_base: http://192.168.200.3:8000/v1
      api_key: "not-needed"

  - model_name: claude-3-5-sonnet-20241022
    litellm_params:
      model: openai/Qwen3-235B-A22B-GPTQ-Int4
      api_base: http://192.168.200.3:8000/v1
      api_key: "not-needed"

general_settings:
  master_key: "sk-local-dev"  # Optional auth
```

#### Start LiteLLM Proxy

```bash
# Run on same machine or accessible network
litellm --config litellm_config.yaml --port 4000 --host 0.0.0.0
```

#### Docker Deployment (alongside vLLM)

```yaml
# docker-compose.yml
version: '3.8'
services:
  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    volumes:
      - ./litellm_config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    environment:
      - LITELLM_MASTER_KEY=sk-local-dev
```

#### Claude Code Configuration

Configure Claude Code to use the LiteLLM proxy:

**Option 1: Environment variable**
```bash
export ANTHROPIC_BASE_URL="http://spark-db71.local:4000"
```

**Option 2: Claude Code settings** (`~/.claude.json` or settings):
```json
{
  "apiBaseUrl": "http://spark-db71.local:4000"
}
```

#### Test the Setup

```bash
# Test via curl (Anthropic format)
curl -X POST "http://localhost:4000/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-local-dev" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-3-opus-20240229",
    "max_tokens": 100,
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'
```

#### Latency Considerations

- LiteLLM adds minimal overhead (~1-5ms per request)
- Main latency is still vLLM inference time
- For local network, proxy overhead is negligible

#### Status

- [ ] Test LiteLLM proxy with vLLM
- [ ] Verify Claude Code can connect
- [ ] Document any additional configuration needed
- [ ] Add to dual Spark setup guide

---

## Future Ideas & Research

### NVFP4 Pre-compilation Investigation

- [ ] **Find a way to pre-compile NVFP4 model kernels**
  - NVFP4 should theoretically be the fastest (native Blackwell FP4 tensor cores)
  - Current blocker: JIT compilation OOMs during model load
  - Questions to investigate:
    - Can we pre-compile on CPU? (Have a workstation with 1TB RAM available)
    - Can compilation be done in pieces/stages?
    - **Pipeline parallel question:** If using layer-parallel (pipeline parallel) instead of tensor parallel, does each DGX Spark only compile its own layers? This could solve the memory issue.
  - Potential approaches:
    - Pre-warm flashinfer cache with dummy model
    - Compile kernels separately before loading weights
    - Use workstation's 1TB RAM for compilation, then transfer cached kernels

### Claude Code Integration

- [ ] **Set up local LLM serving for Claude Code**
  - Claude Code requires Anthropic Messages API format
  - vLLM natively supports OpenAI Chat Completions API
  - **LiteLLM** can translate between Anthropic Messages ↔ OpenAI Chat formats
  - Investigation needed:
    - Does vLLM support Messages API out of box? (Probably not)
    - Set up LiteLLM proxy in front of vLLM
    - Add LiteLLM to the dual Spark setup documentation

### Model Exploration

- [ ] **Find more recent large models (200B+ parameters) supported by vLLM**
  - Candidates to investigate:
    - DeepSeek-R1 variants
    - Llama 4 (when available)
    - Mixtral variants
    - Other MoE models that fit in 256GB with quantization
  - Check vLLM supported architectures list
  - Test which quantization formats work best for each

### Automated Benchmarking

- [ ] **Create automated experiment to find optimal vLLM configuration**
  - Parameters to sweep:
    - `--gpu-memory-utilization` (0.5 to 0.9)
    - `--max-model-len` (various context lengths)
    - `--max-num-seqs` (batch size)
    - `--enforce-eager` vs compiled mode
    - Different quantization formats
  - Metrics to optimize:
    - Output throughput (tok/s)
    - Time to first token (TTFT)
    - P99 latency
  - Output: Best config for dual DGX Spark setup

### Documentation & Sharing

- [ ] **Write blog post about findings**
  - Cover the dual Spark RDMA setup
  - Quantization comparison (GPTQ vs AWQ vs NVFP4)
  - Performance results and recommendations
  - Lessons learned (memory constraints, JIT compilation issues)

- [ ] **Add setup to the community playbook**
  - Refine raw notes into formal playbook format
  - Include troubleshooting guide
  - Add quick-start commands

### Learning Deep Dive

- [ ] **Understand vLLM serving internals (Stretch goal)**
  - Why does vLLM take so long to start compared to llama.cpp?
  - Topics to study:
    - PagedAttention and KV cache management
    - Continuous batching
    - torch.compile and CUDA graph capture
    - Speculative decoding
    - Model parallelism strategies (TP vs PP)
  - Goal: Understand the tradeoffs and when each optimization matters

---

## Claude Code Automation Setup

### Overview

Automated skills for controlling dual DGX Sparks from Mac via Claude Code.

```
┌─────────────┐     SSH      ┌─────────────┐     RDMA     ┌─────────────┐
│    Mac      │─────────────▶│  Spark 1    │◀────────────▶│  Spark 2    │
│ (Claude)    │              │  (Head)     │              │  (Worker)   │
└─────────────┘              └─────────────┘              └─────────────┘
      │                            │                            │
      │ Skills via SSH            Ray Head                  Ray Worker
      └───────────────────────────▶│◀───────────────────────────┘
                                   │
                              vLLM Server (port 8000)
```

### File Structure

```
playbooks/dual-dgx-spark-setup/
├── .env                       # Local config (gitignored)
├── .env.example               # Template for .env
├── benchmarks/
│   ├── RESULTS.md             # Summary table of all runs
│   └── runs/                  # Individual run JSON files
└── SETUP-NOTES-RAW.md

.claude/skills/
├── spark-start/SKILL.md       # Start containers + Ray cluster
├── spark-stop/SKILL.md        # Stop everything cleanly
├── spark-load/SKILL.md        # Load a model into vLLM
├── spark-bench/SKILL.md       # Run benchmark
└── spark-status/SKILL.md      # Check status
```

### Configuration (.env)

```bash
# DGX Spark Hosts
SPARK1_HOST=spark-db71.local
SPARK2_HOST=spark-7ceb.local
SPARK_USER=kecso

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

### Container Startup Command (Critical Environment Variables)

**Spark 1 (Head Node):**
```bash
docker run -d --name vllm-spark \
  --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=192.168.200.3 \
  -e RAY_OVERRIDE_NODE_IP=192.168.200.3 \
  -e VLLM_HOST_IP=192.168.200.3 \
  nvcr.io/nvidia/vllm:26.03-py3 sleep infinity
```

**Spark 2 (Worker Node):**
```bash
docker run -d --name vllm-spark \
  --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=192.168.200.13 \
  -e RAY_OVERRIDE_NODE_IP=192.168.200.13 \
  nvcr.io/nvidia/vllm:26.03-py3 sleep infinity
```

### Ray Cluster Setup

```bash
# Spark 1 (head)
docker exec vllm-spark ray start --head \
  --node-ip-address=192.168.200.3 --port=6379 \
  --dashboard-host=192.168.200.3 --dashboard-port=8265 --num-gpus=1

# Spark 2 (worker)
docker exec vllm-spark ray start \
  --address=192.168.200.3:6379 --node-ip-address=192.168.200.13 --num-gpus=1

# Verify
docker exec vllm-spark ray status  # Should show 2 GPUs
```

### vLLM Server Startup

```bash
# Start with log capture
docker exec vllm-spark bash -c 'python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-235B-A22B-GPTQ-Int4 \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --max-model-len 32768 \
  --host 0.0.0.0 \
  --port 8000 > /tmp/vllm.log 2>&1 &'
```

### Detecting Server Readiness

**Important:** Large models (200B+) take 15-30 minutes to load.

```bash
# Poll /v1/models endpoint (more reliable than /health)
curl -s http://spark-db71.local:8000/v1/models | jq

# Check logs if issues
docker exec vllm-spark tail -50 /tmp/vllm.log
```

### Running Benchmarks

```bash
# From inside container on Spark 1
docker exec vllm-spark vllm bench serve \
  --host 192.168.200.3 \
  --port 8000 \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10 \
  --model Qwen/Qwen3-235B-A22B-GPTQ-Int4
```

### API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List loaded models (use for readiness check) |
| `/v1/chat/completions` | POST | Chat completion (OpenAI format) |
| `/v1/completions` | POST | Text completion |
| `/health` | GET | Basic health check |
| `/metrics` | GET | Prometheus metrics |

```bash
# Query available models
curl -s http://spark-db71.local:8000/v1/models | jq
```

### Test API Request

```bash
curl -X POST "http://spark-db71.local:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
    "messages": [
      {"role": "user", "content": "What is RDMA and why is it useful for AI?"}
    ],
    "max_tokens": 200
  }'
```

### Shutdown

```bash
# Stop Ray on both nodes
docker exec vllm-spark ray stop  # on both Sparks

# Stop and remove containers
docker stop vllm-spark && docker rm vllm-spark  # on both Sparks
```

### Maintenance: Docker Disk Space

**WARNING:** Docker containers accumulate significant disk space over time. Stopped vLLM containers can use 100-400GB each due to cached model weights and compilation artifacts.

```bash
# Check Docker disk usage
docker system df

# Example output showing 2TB in stopped containers:
# TYPE            TOTAL     SIZE      RECLAIMABLE
# Containers      92        1.939TB   1.939TB (100%)
# Build Cache     1167      442GB     375.1GB
# Images          23        223GB     142.8GB

# Clean up stopped containers
docker container prune

# Full cleanup (containers + unused images + build cache)
docker system prune -a

# Preview what will be deleted
docker system prune -a --dry-run
```

**Recommendation:** Run `docker container prune` periodically or after each model testing session.

### Key Lessons Learned

1. **Environment Variables Matter:** Missing `VLLM_HOST_IP`, `RAY_OVERRIDE_NODE_IP`, or `GLOO_SOCKET_IFNAME` causes Ray placement failures or Gloo connection errors.

2. **Health Detection:** The `/v1/models` endpoint is more reliable than `/health` for detecting when vLLM is ready.

3. **Loading Time:** 235B models take 15-30 minutes to load weights and compile CUDA graphs. Be patient.

4. **GPU Utilization:** During loading, nvidia-smi shows 89%+ GPU utilization. After loading, it drops and responds to requests.

5. **Log Capture:** Use `> /tmp/vllm.log 2>&1 &` with docker exec to capture logs for debugging.

---

## Later / Backlog

- [ ] **Explore alternative inference engines**
  - SGLang (fast, good for structured generation)
  - NVIDIA Dynamo / TensorRT-LLM
  - Text Generation Inference (TGI)
  - **Note:** Current focus is mastering vLLM first before exploring alternatives

---

*Raw notes - to be refined into formal playbook*
