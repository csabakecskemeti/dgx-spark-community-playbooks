---
name: spark-status
description: Check status of DGX Spark infrastructure (containers, Ray, vLLM)
allowed-tools: Bash(ssh *) Bash(curl *) Bash(source *) Read
---

# Check DGX Spark Status

## Prerequisites

Source the environment configuration:
```bash
source playbooks/dual-dgx-spark-setup/.env
```

## Steps

1. **Check containers**:
   ```bash
   ssh -t $SPARK1_HOST "docker ps --filter name=$CONTAINER_NAME --format '{{.Names}} {{.Status}}'"
   ssh -t $SPARK2_HOST "docker ps --filter name=$CONTAINER_NAME --format '{{.Names}} {{.Status}}'"
   ```

2. **Check Ray cluster** (if container running):
   ```bash
   ssh -t $SPARK1_HOST "docker exec $CONTAINER_NAME ray status 2>/dev/null || echo 'Ray not running'"
   ```

3. **Check vLLM server**:
   ```bash
   curl -s http://$SPARK1_HOST:8000/health || echo "vLLM not responding"
   curl -s http://$SPARK1_HOST:8000/v1/models || echo "No models loaded"
   ```

4. Report status summary showing:
   - Container status on both Sparks
   - Ray cluster state (nodes, GPUs)
   - vLLM server health and loaded model (if any)
