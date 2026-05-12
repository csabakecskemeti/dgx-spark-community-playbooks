# LiteLLM Proxy for Claude Code

Use LiteLLM to expose vLLM with an Anthropic-compatible API, enabling Claude Code to use your local DGX Spark models.

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ Claude Code │ ───► │   LiteLLM   │ ───► │    vLLM     │ ───► │  DGX Spark  │
│   (Mac)     │      │  (port 4000)│      │ (port 8000) │      │    GPU      │
│             │      │ Anthropic   │      │  OpenAI API │      │             │
│             │      │ Messages API│      │             │      │             │
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
```

LiteLLM translates Anthropic Messages API ↔ OpenAI Chat Completions API.

## Placeholder Reference

Throughout this document, replace these placeholders with your values:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `<SPARK1_HOST>` | Hostname of the Spark running vLLM | `spark1.local` |
| `<SPARK2_HOST>` | Hostname of worker Spark (if dual setup) | `spark2.local` |

## Prerequisites

### vLLM with Tool Calling

vLLM **must** be running with tool calling enabled:

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

**Critical flags:**
- `--enable-auto-tool-choice` - Enables tool/function calling
- `--tool-call-parser qwen3_xml` - Parser for Qwen 3.6 tool format

Without these, Claude Code's tool calls will fail.

## Setup on DGX Spark

### 1. Create Configuration

On the Spark running vLLM (e.g., <SPARK1_HOST>):

```bash
mkdir -p ~/spark_litellm_claude
cd ~/spark_litellm_claude

cat > litellm-config.yaml << 'EOF'
model_list:
  - model_name: claude-*
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://localhost:8000/v1
      api_key: not-needed
    model_info:
      max_tokens: 262144

  - model_name: Qwen/Qwen3.6-35B-A3B-FP8
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://localhost:8000/v1
      api_key: not-needed
    model_info:
      max_tokens: 262144

litellm_settings:
  drop_params: true
  request_timeout: 600
  modify_params: true

general_settings:
  disable_key_check: true
EOF
```

**Configuration explained:**

| Setting | Purpose |
|---------|---------|
| `claude-*` | Wildcard matches any Claude model name |
| `Qwen/Qwen3.6-35B-A3B-FP8` | Allows using the real model name |
| `hosted_vllm/` | Tells LiteLLM to use vLLM provider |
| `drop_params: true` | Ignores Anthropic-only parameters |
| `modify_params: true` | Adapts request format for OpenAI API |
| `disable_key_check: true` | No API key validation needed |
| `request_timeout: 600` | 10 min timeout for long generations |

### 2. Run LiteLLM

**Note:** Docker image doesn't support ARM64 (DGX Spark uses Grace CPU). Use pip instead.

```bash
# Install
pip install 'litellm[proxy]'

# Run (foreground)
litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0

# Or run in background
nohup litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0 > litellm.log 2>&1 &
```

Alternative with uv:
```bash
uv tool install 'litellm[proxy]'
litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0
```

### 3. Verify LiteLLM

**Check process is running:**
```bash
ps aux | grep litellm
```

**Test with Claude model name (aliased):**
```bash
curl -X POST "http://localhost:4000/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: dummy" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Hi"}]
  }'
```

**Test with real model name:**
```bash
curl -X POST "http://localhost:4000/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: dummy" \
  -d '{
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Hi"}]
  }'
```

Both should return a response with the model generating text.

## Configure Claude Code

On your Mac (or wherever Claude Code runs):

### Set Environment Variable

```bash
export ANTHROPIC_BASE_URL="http://<SPARK1_HOST>:4000"
```

Or add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
echo 'export ANTHROPIC_BASE_URL="http://<SPARK1_HOST>:4000"' >> ~/.zshrc
source ~/.zshrc
```

### Run Claude Code

**Using Claude model alias:**
```bash
claude --model claude-3-5-sonnet-20241022
```

**Using real model name:**
```bash
claude --model Qwen/Qwen3.6-35B-A3B-FP8
```

Both work - LiteLLM routes them to your local vLLM server.

## Tested Configuration

**Verified working on:**
- Dual DGX Spark cluster
- vLLM with Qwen/Qwen3.6-35B-A3B-FP8 (TP=2 across dual Spark)
- LiteLLM installed via `uv tool install 'litellm[proxy]'`
- Claude Code with local model inference

**Exact working config (`~/spark_litellm_claude/litellm-config.yaml`):**
```yaml
model_list:
  - model_name: claude-*
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://localhost:8000/v1
      api_key: not-needed
    model_info:
      max_tokens: 262144

  - model_name: Qwen/Qwen3.6-35B-A3B-FP8
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://localhost:8000/v1
      api_key: not-needed
    model_info:
      max_tokens: 262144

litellm_settings:
  drop_params: true
  request_timeout: 600
  modify_params: true

general_settings:
  disable_key_check: true
```

**Run command:**
```bash
cd ~/spark_litellm_claude
litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0
```

**Test commands verified:**
```bash
# Both return valid responses
curl -X POST "http://<SPARK1_HOST>:4000/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: dummy" \
  -d '{"model": "claude-3-5-sonnet-20241022", "max_tokens": 50, "messages": [{"role": "user", "content": "Hi"}]}'

curl -X POST "http://<SPARK1_HOST>:4000/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: dummy" \
  -d '{"model": "Qwen/Qwen3.6-35B-A3B-FP8", "max_tokens": 50, "messages": [{"role": "user", "content": "Hi"}]}'
```

## Claude Code Context Compaction

**Important discovery:** Using the `claude-*` wildcard route enables Claude Code's automatic context compaction feature.

When Claude Code thinks it's talking to a Claude model (via the `claude-*` alias), it automatically manages context length by compacting older conversation history. This is a significant benefit for long coding sessions.

**Recommendation:** Use `claude --model claude-3-5-sonnet-20241022` rather than the real model name to benefit from context compaction.

## Switching Between Local and Anthropic

**Use local model:**
```bash
export ANTHROPIC_BASE_URL="http://<SPARK1_HOST>:4000"
claude
```

**Use Anthropic API:**
```bash
unset ANTHROPIC_BASE_URL
claude
```

## Stopping Services

```bash
# Stop LiteLLM (if running in background)
pkill -f "litellm --config"

# Stop vLLM (if needed)
docker stop vllm_node && docker rm vllm_node
```

## Troubleshooting

### LiteLLM can't reach vLLM

Check vLLM is accessible:
```bash
curl http://localhost:8000/v1/models
```

### Tool calls not working

Ensure vLLM was started with:
- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_xml`

### Timeout errors

Increase timeout in config:
```yaml
litellm_settings:
  request_timeout: 900  # 15 minutes
```

### Claude Code hangs

Check LiteLLM logs:
```bash
# If running with nohup
tail -50 litellm.log

# Or check process
ps aux | grep litellm
```

## Vision Models

> **Note:** Vision model support with vLLM + LiteLLM has not been tested yet.
> For vision-capable local inference (e.g., for [claude-autopilot-sandbox](https://github.com/csabakecskemeti/claude-autopilot-sandbox)), consider using [LM Studio](https://lmstudio.ai/) with a GGUF vision model as an alternative.

## Related Tools

- **[quasar-deck](https://github.com/csabakecskemeti/quasar-deck)** - Cluster monitoring utility for DGX Spark
- **[claude-autopilot-sandbox](https://github.com/csabakecskemeti/claude-autopilot-sandbox)** - Claude Code automation sandbox

## Security Notes

- LiteLLM is third-party software not maintained by Anthropic
- Use verified versions (avoid 1.82.7-1.82.8 which had security issues)
- Consider firewall rules if exposing beyond localhost

## Alternative: Run LiteLLM on Mac

If you prefer running LiteLLM locally:

```bash
# Install
uv tool install 'litellm[proxy]'

# Update config to point to Spark
cat > litellm-config.yaml << 'EOF'
model_list:
  - model_name: claude-*
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://<SPARK1_HOST>:8000/v1
      api_key: "not-needed"
    model_info:
      max_tokens: 262144

litellm_settings:
  drop_params: true
  request_timeout: 600
  modify_params: true

general_settings:
  disable_key_check: true
EOF

# Run
litellm --config litellm-config.yaml --port 4000

# Configure Claude Code
export ANTHROPIC_BASE_URL="http://localhost:4000"
claude
```
