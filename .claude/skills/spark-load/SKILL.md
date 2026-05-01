---
name: spark-load
description: Load a model into vLLM on dual DGX Spark
argument-hint: model-name [--enforce-eager] [--gpu-mem 0.7]
allowed-tools: Bash(ssh *) Bash(curl *) Bash(source *) Read
---

# Load Model into vLLM

Arguments: $ARGUMENTS (e.g., "Qwen/Qwen3-235B-A22B-GPTQ-Int4 --enforce-eager")

## Prerequisites

Source the environment configuration:
```bash
source playbooks/dual-dgx-spark-setup/.env
```

## Steps

1. Parse model name and options from $ARGUMENTS
   - First argument is the model name
   - Optional flags: `--enforce-eager`, `--gpu-mem <value>`
   - Use $DEFAULT_GPU_MEM from .env if not specified
   - Use $DEFAULT_MAX_MODEL_LEN from .env for max model length

2. Start vLLM server with log capture:
   ```bash
   ssh $SPARK1_HOST "docker exec $CONTAINER_NAME bash -c 'python -m vllm.entrypoints.openai.api_server \
     --model <MODEL> \
     --tensor-parallel-size 2 \
     --distributed-executor-backend ray \
     --gpu-memory-utilization $DEFAULT_GPU_MEM \
     --max-model-len $DEFAULT_MAX_MODEL_LEN \
     --host 0.0.0.0 \
     --port 8000 \
     [OPTIONS] > /tmp/vllm.log 2>&1 &'"
   ```

3. Wait for server to be ready by checking `/v1/models` endpoint:
   - The 235B model takes 15-30 minutes to load
   - Poll every 30 seconds: `curl -s http://$SPARK1_HOST:8000/v1/models`
   - Server is ready when it returns JSON with model data (not empty/error)
   - **DO NOT** read logs repeatedly - just poll the endpoint

4. If issues occur, check logs:
   ```bash
   ssh $SPARK1_HOST "docker exec $CONTAINER_NAME tail -50 /tmp/vllm.log"
   ```

5. Report model loaded and ready

## Notes

- Large models (200B+) take 15-30 minutes to load weights and compile CUDA graphs
- The `/v1/models` endpoint is more reliable than `/health` for detecting readiness
- GPU utilization (nvidia-smi) shows 89%+ during loading, drops after ready
