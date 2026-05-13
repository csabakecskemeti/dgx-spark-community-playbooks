# Dual DGX Spark Distributed Inference

Run large language models (200B+) across two DGX Sparks connected via 200Gbps RDMA.

## Architecture

```
┌─────────────────┐                              ┌─────────────────┐
│   DGX Spark 1   │◄────── 200Gbps RDMA ────────►│   DGX Spark 2   │
│   (Head Node)   │        Direct Connect        │   (Worker)      │
│                 │                              │                 │
│  ┌───────────┐  │                              │  ┌───────────┐  │
│  │  GB10 GPU │  │                              │  │  GB10 GPU │  │
│  │  128GB    │  │                              │  │  128GB    │  │
│  └───────────┘  │                              │  └───────────┘  │
│                 │                              │                 │
│  ConnectX-7     │                              │  ConnectX-7     │
└─────────────────┘                              └─────────────────┘
        │                                                │
        └──────────────── Ray Cluster ───────────────────┘
                              │
                    ┌─────────────────┐
                    │  vLLM Server    │
                    │  Tensor Parallel│
                    │  Size = 2       │
                    └─────────────────┘
```

## Hardware Requirements

| Component | Specification |
|-----------|--------------|
| Nodes | 2× NVIDIA DGX Spark |
| GPU | Grace Blackwell GB10 (128GB unified memory each) |
| Interconnect | ConnectX-7 200GbE (direct QSFP cable) |
| Total Memory | 256GB unified GPU memory |

## Quick Start

### 1. Network Setup
Configure RDMA interfaces on both nodes. See [01-hardware-network.md](01-hardware-network.md).

### 2. Container & Ray Setup
Start Docker containers with proper RDMA/NCCL environment variables. See [02-docker-ray-setup.md](02-docker-ray-setup.md).

### 3. Run Inference
Choose your framework:
- **[vLLM (NGC Container)](frameworks/vllm/)** - Production-ready, best GPTQ performance (vLLM 0.17.1)
- **[SGLang](frameworks/sglang/)** - Coming soon

### 4. Claude Code Integration (Optional)
Use your local vLLM as inference backend for Claude Code:
- **[Local Claude Code on DGX Spark](../local-claude-code-dgx-spark/)** - Complete setup with spark-vllm-docker + LiteLLM

## Performance Results

### NGC vLLM Container (26.03)
| Model | Quantization | Throughput | TTFT | Status |
|-------|--------------|------------|------|--------|
| Qwen3-235B-A22B | GPTQ-Int4 | **150 tok/s** | 36s | Stable |
| Qwen3-235B-A22B | AWQ | 141 tok/s | 35s | Stable |
| Qwen3-235B-A22B | NVFP4 | 84 tok/s | 24s | Unstable |

**Recommendation:** Use GPTQ-Int4 for 235B models.

For newer models (Qwen 3.6+) with latest vLLM, see [Local Claude Code on DGX Spark](../local-claude-code-dgx-spark/).

## Key Findings

1. **GPTQ outperforms NVFP4** on current vLLM (26.03) due to pre-compiled Marlin kernels
2. **200Gbps bidirectional** RDMA achieved with direct QSFP connection
3. **PCIe x4 bottleneck** limits unidirectional to ~100Gbps, but bidirectional workloads (NCCL) utilize full bandwidth
4. **Critical environment variables** for distributed inference:
   - `VLLM_HOST_IP` - Forces vLLM to use RDMA interface
   - `GLOO_SOCKET_IFNAME` - Required for Gloo backend
   - `RAY_OVERRIDE_NODE_IP` - Ensures Ray uses correct IP

## Documentation

| Document | Description |
|----------|-------------|
| [01-hardware-network.md](01-hardware-network.md) | RDMA setup, netplan, IP addressing |
| [02-docker-ray-setup.md](02-docker-ray-setup.md) | Container commands, Ray cluster |
| [frameworks/vllm/](frameworks/vllm/) | NGC vLLM container setup and benchmarks |
| [frameworks/sglang/](frameworks/sglang/) | SGLang setup (coming soon) |
| [troubleshooting.md](troubleshooting.md) | Common issues and solutions |
| [SETUP-NOTES-RAW.md](SETUP-NOTES-RAW.md) | Detailed working notes |

## Claude Code Integration

See **[Local Claude Code on DGX Spark](../local-claude-code-dgx-spark/)** playbook for:
- Latest vLLM builds via spark-vllm-docker
- LiteLLM proxy for Anthropic API compatibility
- Claude Code configuration

## Related Tools

- **[quasar-deck](https://github.com/csabakecskemeti/quasar-deck)** - Cluster monitoring utility for DGX Spark

## License

MIT
