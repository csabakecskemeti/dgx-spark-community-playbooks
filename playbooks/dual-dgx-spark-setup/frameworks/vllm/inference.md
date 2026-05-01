# vLLM Inference Guide

## Prerequisites

- Containers running on both Sparks (see [../../02-docker-ray-setup.md](../../02-docker-ray-setup.md))
- Ray cluster active with 2 GPUs

Verify Ray cluster:
```bash
docker exec vllm-spark ray status
# Should show: 0.0/2.0 GPU
```

## Starting the Server

### Basic Command

```bash
docker exec vllm-spark python -m vllm.entrypoints.openai.api_server \
  --model <MODEL_NAME> \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --max-model-len 32768 \
  --host 0.0.0.0 \
  --port 8000
```

### With Log Capture (Background)

```bash
docker exec vllm-spark bash -c 'python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-235B-A22B-GPTQ-Int4 \
  --tensor-parallel-size 2 \
  --distributed-executor-backend ray \
  --gpu-memory-utilization 0.7 \
  --max-model-len 32768 \
  --host 0.0.0.0 \
  --port 8000 > /tmp/vllm.log 2>&1 &'
```

Check logs:
```bash
docker exec vllm-spark tail -50 /tmp/vllm.log
```

## Server Options

| Option | Description | Recommended |
|--------|-------------|-------------|
| `--tensor-parallel-size` | Number of GPUs | 2 |
| `--distributed-executor-backend` | Ray or mp | ray |
| `--gpu-memory-utilization` | GPU memory fraction | 0.7 |
| `--max-model-len` | Max context length | 32768 |
| `--enforce-eager` | Disable compilation | For debugging |

### Memory Tips

- DGX Spark has unified memory (CPU+GPU share 128GB)
- Use `--gpu-memory-utilization 0.7` to leave headroom for KV cache
- 235B MoE models need ~60GB per node with GPTQ

## Detecting Server Readiness

Large models (200B+) take 15-30 minutes to load.

**Poll `/v1/models` endpoint** (more reliable than `/health`):
```bash
curl -s http://<spark1-host>:8000/v1/models | jq
```

Server is ready when it returns:
```json
{
  "data": [
    {"id": "Qwen/Qwen3-235B-A22B-GPTQ-Int4", ...}
  ]
}
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List loaded models |
| `/v1/chat/completions` | POST | Chat completion (OpenAI format) |
| `/v1/completions` | POST | Text completion |
| `/health` | GET | Basic health check |
| `/metrics` | GET | Prometheus metrics |

## API Usage Examples

### Chat Completion

```bash
curl -X POST "http://<spark1-host>:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain tensor parallelism."}
    ],
    "max_tokens": 500,
    "temperature": 0.7
  }'
```

### Streaming Response

```bash
curl -X POST "http://<spark1-host>:8000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
    "messages": [{"role": "user", "content": "Write a poem about GPUs."}],
    "max_tokens": 200,
    "stream": true
  }'
```

### Text Completion

```bash
curl -X POST "http://<spark1-host>:8000/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
    "prompt": "The future of AI is",
    "max_tokens": 100
  }'
```

## Supported Models

### Tested & Recommended

| Model | Quantization | Status | Notes |
|-------|--------------|--------|-------|
| Qwen/Qwen3-235B-A22B-GPTQ-Int4 | GPTQ | **Recommended** | Best performance |
| QuixiAI/Qwen3-235B-A22B-AWQ | AWQ | Good | Slightly slower |
| Qwen/Qwen3-4B-Instruct | BF16 | Good | For testing |

### Not Recommended (Yet)

| Model | Issue |
|-------|-------|
| nvidia/*-NVFP4 | JIT compilation OOM, unstable on multi-node |
| Qwen/Qwen3-235B-A22B-FP8 | OOM (too large for 256GB) |

## Quantization Comparison

| Format | Memory | Throughput | Stability |
|--------|--------|------------|-----------|
| **GPTQ-Int4** | ~60GB | **150 tok/s** | Stable |
| AWQ-Int4 | ~60GB | 141 tok/s | Stable |
| NVFP4 | ~60GB | 84 tok/s | Unstable |
| FP8 | ~235GB | OOM | N/A |

## Troubleshooting

### Server Won't Start

Check Ray cluster status:
```bash
docker exec vllm-spark ray status
```

Check logs:
```bash
docker exec vllm-spark tail -100 /tmp/vllm.log
```

### OOM During Loading

- Reduce `--gpu-memory-utilization` to 0.6
- Reduce `--max-model-len` to 16384
- Use a smaller quantized model

### Slow First Response

Normal for large models. The first request triggers:
1. CUDA graph capture
2. KV cache allocation
3. Warmup compilation

Subsequent requests will be faster.

## Next Steps

- [Benchmarking Guide](benchmarking.md)
- [Claude Code Skills](skills/)
