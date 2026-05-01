---
name: spark-stop
description: Stop vLLM, Ray, and containers on dual DGX Spark
allowed-tools: Bash(ssh *) Bash(docker *) Bash(source *) Read
---

# Stop DGX Spark Infrastructure

## Prerequisites

Source the environment configuration:
```bash
source playbooks/dual-dgx-spark-setup/.env
```

## Steps

1. **Stop Ray on both nodes**:
   ```bash
   ssh -t $SPARK1_HOST "docker exec $CONTAINER_NAME ray stop" &
   ssh -t $SPARK2_HOST "docker exec $CONTAINER_NAME ray stop" &
   wait
   ```

2. **Stop and remove containers**:
   ```bash
   ssh -t $SPARK1_HOST "docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME" &
   ssh -t $SPARK2_HOST "docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME" &
   wait
   ```

3. Verify cleanup with `/spark-status`
