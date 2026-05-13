# Local Claude Code on DGX Spark

Run Claude Code with local LLM inference on your DGX Spark cluster.

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Claude Code │ ───► │   LiteLLM   │ ───► │    vLLM     │ ───► │  DGX Spark  │
│   (Mac)     │      │  (port 4000)│      │ (port 8000) │      │    GPU      │
│             │      │ Anthropic   │      │  OpenAI API │      │             │
│             │      │ Messages API│      │             │      │             │
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
```

**Components:**
- **vLLM** - High-performance inference server (OpenAI-compatible API)
- **LiteLLM** - API translation layer (Anthropic Messages API → OpenAI Chat API)
- **Claude Code** - Anthropic's coding assistant CLI

## Quick Start

### 1. Set up vLLM on DGX Spark

See [01-vllm-setup.md](01-vllm-setup.md) for full instructions.

```bash
# On DGX Spark
cd ~
git clone https://github.com/eugr/spark-vllm-docker.git
cd spark-vllm-docker
./build-and-copy.sh
./hf-download.sh Qwen/Qwen3.6-35B-A3B-FP8
./run-recipe.sh qwen3.6-35b-a3b-fp8
```

### 2. Set up LiteLLM Proxy

See [02-litellm-proxy.md](02-litellm-proxy.md) for full instructions.

```bash
# On DGX Spark (same node as vLLM)
pip install 'litellm[proxy]'

# Create config (see 02-litellm-proxy.md for full template)
cat > litellm-config.yaml << 'EOF'
model_list:
  - model_name: claude-*
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://localhost:8000/v1
      api_key: not-needed

litellm_settings:
  drop_params: true
  request_timeout: 600
  modify_params: true

general_settings:
  disable_key_check: true
EOF

litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0
```

### 3. Configure Claude Code

```bash
# On your Mac
export ANTHROPIC_BASE_URL="http://<SPARK_HOST>:4000"
claude --model claude-3-5-sonnet-20241022
```

## Performance

| Configuration | Throughput | TTFT | Use Case |
|--------------|------------|------|----------|
| Single Spark | 214 tok/s | 2.5s | Interactive coding |
| Dual Spark (TP=2) | 550 tok/s | 4.2s | High throughput / larger models |

## Documentation

| Document | Description |
|----------|-------------|
| [01-vllm-setup.md](01-vllm-setup.md) | vLLM server setup (single & dual Spark) |
| [02-litellm-proxy.md](02-litellm-proxy.md) | LiteLLM proxy configuration |
| [.env.example](.env.example) | Environment configuration template |

## Key Benefits

- **Context compaction**: Using `claude-*` model alias enables Claude Code's automatic context management
- **Tool calling**: Full support with `--enable-auto-tool-choice --tool-call-parser qwen3_xml`
- **Local inference**: No API costs, data stays on your network
- **Dual Spark scaling**: 2.5x throughput with tensor parallelism over RDMA

## Requirements

- NVIDIA DGX Spark (1 or 2 nodes)
- [spark-vllm-docker](https://github.com/eugr/spark-vllm-docker) for latest vLLM builds
- Python 3.10+ for LiteLLM

## Related

- **[claude-autopilot-sandbox](https://github.com/csabakecskemeti/claude-autopilot-sandbox)** - Containerized Claude Code environment for autonomous coding tasks. Combine with this playbook for fully local AI-assisted development.
- **[quasar-deck](https://github.com/csabakecskemeti/quasar-deck)** - Cluster monitoring for DGX Spark
