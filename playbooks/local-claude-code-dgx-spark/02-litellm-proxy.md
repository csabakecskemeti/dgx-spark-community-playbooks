# LiteLLM Proxy Setup

LiteLLM translates Anthropic Messages API to OpenAI Chat Completions API, enabling Claude Code to use your local vLLM server.

## Prerequisites

vLLM must be running with tool calling enabled (see [01-vllm-setup.md](01-vllm-setup.md)):
- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_xml`

## Setup on DGX Spark

### 1. Install LiteLLM

**Note:** Docker image doesn't support ARM64 (DGX Spark uses Grace CPU). Use pip.

```bash
pip install 'litellm[proxy]'
```

Or with uv:
```bash
uv tool install 'litellm[proxy]'
```

### 2. Create Configuration

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
| `hosted_vllm/` | Tells LiteLLM to use vLLM provider |
| `drop_params: true` | Ignores Anthropic-only parameters |
| `modify_params: true` | Adapts request format for OpenAI API |
| `request_timeout: 600` | 10 min timeout for long generations |

### 3. Run LiteLLM

```bash
# Foreground
litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0

# Or background
nohup litellm --config litellm-config.yaml --port 4000 --host 0.0.0.0 > litellm.log 2>&1 &
```

### 4. Verify

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

## Configure Claude Code

On your Mac (or wherever Claude Code runs):

### Set Environment Variable

```bash
export ANTHROPIC_BASE_URL="http://<SPARK_HOST>:4000"
```

Or add to shell profile:
```bash
echo 'export ANTHROPIC_BASE_URL="http://<SPARK_HOST>:4000"' >> ~/.zshrc
source ~/.zshrc
```

### Run Claude Code

```bash
claude --model claude-3-5-sonnet-20241022
```

## Context Compaction

Using the `claude-*` wildcard route enables Claude Code's automatic context compaction feature. When Claude Code thinks it's talking to a Claude model, it automatically manages context length by compacting older conversation history.

**Recommendation:** Use `claude --model claude-3-5-sonnet-20241022` to benefit from context compaction.

## Switching Between Local and Anthropic

```bash
# Use local model
export ANTHROPIC_BASE_URL="http://<SPARK_HOST>:4000"
claude

# Use Anthropic API
unset ANTHROPIC_BASE_URL
claude
```

## Alternative: Run LiteLLM on Mac

If you prefer running LiteLLM locally instead of on the Spark:

```bash
uv tool install 'litellm[proxy]'

cat > litellm-config.yaml << 'EOF'
model_list:
  - model_name: claude-*
    litellm_params:
      model: hosted_vllm/Qwen/Qwen3.6-35B-A3B-FP8
      api_base: http://<SPARK_HOST>:8000/v1
      api_key: not-needed

litellm_settings:
  drop_params: true
  request_timeout: 600
  modify_params: true

general_settings:
  disable_key_check: true
EOF

litellm --config litellm-config.yaml --port 4000

export ANTHROPIC_BASE_URL="http://localhost:4000"
claude
```

## Stopping

```bash
pkill -f "litellm --config"
```

## Troubleshooting

### LiteLLM can't reach vLLM

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
tail -50 litellm.log
```

## Security Notes

- LiteLLM is third-party software not maintained by Anthropic
- Consider firewall rules if exposing beyond localhost
