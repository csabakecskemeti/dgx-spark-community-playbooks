# vLLM Distributed Inference

Run vLLM with tensor parallelism across two DGX Sparks.

## Quick Start

1. **Start containers and Ray cluster** (see [../../02-docker-ray-setup.md](../../02-docker-ray-setup.md))

2. **Load a model:**
   ```bash
   docker exec vllm-spark python -m vllm.entrypoints.openai.api_server \
     --model Qwen/Qwen3-235B-A22B-GPTQ-Int4 \
     --tensor-parallel-size 2 \
     --distributed-executor-backend ray \
     --gpu-memory-utilization 0.7 \
     --max-model-len 32768 \
     --host 0.0.0.0 \
     --port 8000
   ```

3. **Test the API:**
   ```bash
   curl -X POST "http://<spark1-host>:8000/v1/chat/completions" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
       "messages": [{"role": "user", "content": "Hello!"}],
       "max_tokens": 100
     }'
   ```

## Container Version

**Recommended:** `nvcr.io/nvidia/vllm:26.03-py3` (vLLM 0.17.1)

| Container | vLLM Version | Notes |
|-----------|--------------|-------|
| 26.02-py3 | 0.15.1 | NVFP4 broken on Blackwell |
| **26.03-py3** | **0.17.1** | Recommended for DGX Spark |

## Documentation

| Document | Description |
|----------|-------------|
| [inference.md](inference.md) | Model loading, server options, API usage |
| [benchmarking.md](benchmarking.md) | How to benchmark, results, comparison |
| [skills/](skills/) | Claude Code automation skills |

## Recommended Models

| Model | Quantization | Memory | Throughput |
|-------|--------------|--------|------------|
| Qwen/Qwen3-235B-A22B-GPTQ-Int4 | GPTQ | ~60GB | **150 tok/s** |
| QuixiAI/Qwen3-235B-A22B-AWQ | AWQ | ~60GB | 141 tok/s |

## Configuration

Copy and edit `.env.example`:
```bash
cp .env.example .env
```

See [.env.example](.env.example) for all available settings.
