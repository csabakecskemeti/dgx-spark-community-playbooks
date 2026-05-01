---
name: spark-bench
description: Run vLLM benchmark on dual DGX Spark and record results
argument-hint: [model-name]
allowed-tools: Bash(*) Read Write Edit
---

# Run Benchmark

Run `vllm bench serve` locally (connects to Spark 1) and record results.

## Prerequisites

Source the environment configuration:
```bash
source playbooks/dual-dgx-spark-setup/.env
```

## Steps

1. Get model name from $ARGUMENTS or detect from running server:
   ```bash
   curl -s http://$SPARK1_HOST:8000/v1/models | jq -r '.data[0].id'
   ```

2. Run benchmark using env vars for defaults:
   ```bash
   vllm bench serve \
     --host $SPARK1_RDMA_IP \
     --port 8000 \
     --random-input-len $BENCH_INPUT_LEN \
     --random-output-len $BENCH_OUTPUT_LEN \
     --num-prompts $BENCH_NUM_PROMPTS \
     --request-rate $BENCH_REQUEST_RATE \
     --model <MODEL>
   ```

3. Parse results (throughput, TTFT, TPOT)

4. Save to `playbooks/dual-dgx-spark-setup/benchmarks/runs/<timestamp>_<model>.json`:
   ```json
   {
     "timestamp": "<ISO8601>",
     "model": "<MODEL>",
     "container": "<VLLM_CONTAINER>",
     "config": {
       "gpu_mem": "<DEFAULT_GPU_MEM>",
       "max_model_len": "<DEFAULT_MAX_MODEL_LEN>",
       "input_len": "<BENCH_INPUT_LEN>",
       "output_len": "<BENCH_OUTPUT_LEN>",
       "num_prompts": "<BENCH_NUM_PROMPTS>",
       "request_rate": "<BENCH_REQUEST_RATE>"
     },
     "results": { "throughput": ..., "ttft_mean": ..., "tpot_mean": ... }
   }
   ```

5. Update `playbooks/dual-dgx-spark-setup/benchmarks/RESULTS.md` summary table

6. Report results summary
