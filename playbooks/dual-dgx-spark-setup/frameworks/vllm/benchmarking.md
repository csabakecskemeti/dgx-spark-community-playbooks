# vLLM Benchmarking Guide

## Running Benchmarks

Use `vllm bench serve` inside the container to benchmark the running server.

### Basic Benchmark

```bash
docker exec vllm-spark vllm bench serve \
  --host <SPARK1_RDMA_IP> \
  --port 8000 \
  --model <MODEL_NAME> \
  --random-input-len 2048 \
  --random-output-len 2000 \
  --num-prompts 50 \
  --request-rate 10
```

### Benchmark Options

| Option | Description | Default |
|--------|-------------|---------|
| `--random-input-len` | Input prompt length | 2048 |
| `--random-output-len` | Output length | 2000 |
| `--num-prompts` | Number of requests | 50 |
| `--request-rate` | Requests per second | 10 |

## Example Output

```
============ Serving Benchmark Result ============
Successful requests:                     50
Failed requests:                         0
Benchmark duration (s):                  663.05
Total input tokens:                      102,400
Total generated tokens:                  100,000
--------------------------------------------------
Output token throughput (tok/s):         150.82
Peak output token throughput (tok/s):    200.00
Total token throughput (tok/s):          305.26
--------------------------------------------------
Mean TTFT (ms):                          36,210
Median TTFT (ms):                        34,233
P99 TTFT (ms):                           73,511
--------------------------------------------------
Mean TPOT (ms):                          310.17
Median TPOT (ms):                        311.30
P99 TPOT (ms):                           325.31
==================================================
```

## Key Metrics

| Metric | Description | Good Value |
|--------|-------------|------------|
| **Output throughput** | Tokens generated per second | >100 tok/s |
| **TTFT** | Time to first token | <60s for 235B |
| **TPOT** | Time per output token | <400ms |
| **Failed requests** | Should be 0 | 0 |

## Benchmark Results

### Qwen3-235B-A22B (Dual DGX Spark, TP=2)

| Quantization | Throughput | TTFT | TPOT | Status |
|--------------|------------|------|------|--------|
| **GPTQ-Int4** | **150 tok/s** | 36s | 310ms | Stable |
| AWQ | 141 tok/s | 35s | 332ms | Stable |
| NVFP4 (eager) | 84 tok/s | 24s | 334ms | Unstable |

### Key Findings

1. **GPTQ-Int4 is the best choice** for DGX Spark
   - Pre-compiled Marlin kernels
   - No JIT compilation overhead
   - Consistent performance

2. **AWQ is a close second** (~5% slower)
   - May have quality advantages for some models
   - Same memory footprint as GPTQ

3. **NVFP4 underperforms** without compilation
   - Native Blackwell FP4 tensor cores unused in eager mode
   - JIT compilation causes OOM on dual-node setup
   - Wait for vLLM to ship pre-compiled kernels

## Saving Results

### JSON Format

```bash
# Manual save
docker exec vllm-spark vllm bench serve ... > benchmark_output.txt

# Parse and save (example structure)
{
  "timestamp": "2026-04-27T21:40:02Z",
  "model": "Qwen/Qwen3-235B-A22B-GPTQ-Int4",
  "container": "nvcr.io/nvidia/vllm:26.03-py3",
  "config": {
    "tensor_parallel_size": 2,
    "gpu_memory_utilization": 0.7,
    "max_model_len": 32768
  },
  "benchmark": {
    "input_len": 2048,
    "output_len": 2000,
    "num_prompts": 50,
    "request_rate": 10
  },
  "results": {
    "output_throughput_toks": 150.82,
    "ttft_mean_ms": 36210,
    "tpot_mean_ms": 310.17
  }
}
```

## Performance Tips

### Maximize Throughput

1. **Use GPTQ-Int4** quantization
2. **Set `--gpu-memory-utilization 0.7`** - leaves room for KV cache
3. **Use `--max-model-len 32768`** for long context
4. **Don't use `--enforce-eager`** - compilation improves performance

### Reduce TTFT

1. Use smaller `--max-model-len` if you don't need long context
2. First request is always slower (warmup)
3. MoE models (like Qwen3-235B) have faster TTFT than dense models

### Consistent Results

1. Run multiple benchmark rounds
2. Discard first run (warmup)
3. Average 3-5 runs for reliable numbers

## Comparing Models

When comparing models, keep consistent:
- Same input/output lengths
- Same number of prompts
- Same request rate
- Same hardware configuration

## Results Directory

Store benchmark results in:
```
playbooks/dual-dgx-spark-setup/benchmarks/
├── RESULTS.md          # Summary table
└── runs/               # Individual JSON files
    ├── 2026-04-27_Qwen3-235B-GPTQ.json
    └── ...
```
