# Troubleshooting Guide

Common issues and solutions for dual DGX Spark distributed inference.

## Quick Diagnostics

Run these commands to identify most issues:

```bash
# Check container status
ssh spark1.local "docker ps -a --filter name=vllm-spark"

# Check Ray cluster
ssh spark1.local "docker exec vllm-spark ray status"

# Check vLLM server
curl -s http://spark1.local:8000/v1/models | jq

# Check NCCL connectivity
ssh spark1.local "docker exec vllm-spark python /path/to/test_nccl.py"
```

## Network Issues

### RDMA Not Working

**Symptoms:**
- Slow model loading (hours instead of minutes)
- Low throughput during inference
- NCCL errors mentioning "socket" fallback

**Diagnosis:**
```bash
# Check RDMA devices
ssh spark1.local "ibstat"
ssh spark1.local "ibv_devices"

# Check link status
ssh spark1.local "ip link show enp1s0f1np1"
```

**Solutions:**

1. **Verify RDMA interface IP configuration:**
   ```bash
   ssh spark1.local "ip addr show enp1s0f1np1"
   # Should show 192.168.1.X/24
   ```

2. **Check netplan configuration:**
   ```bash
   ssh spark1.local "cat /etc/netplan/99-rdma.yaml"
   ```

3. **Test connectivity:**
   ```bash
   ssh spark1.local "ping -c 3 192.168.1.2"  # Ping Spark 2
   ```

4. **Reapply netplan if needed:**
   ```bash
   ssh spark1.local "sudo netplan apply"
   ```

### Container Can't See RDMA

**Symptoms:**
- `ibv_devices` returns empty inside container
- NCCL falls back to TCP

**Solution:** Ensure container is started with InfiniBand mounts:
```bash
docker run ... \
  -v /dev/infiniband:/dev/infiniband \
  --privileged \
  ...
```

## Ray Cluster Issues

### Ray Worker Won't Join

**Symptoms:**
- `ray status` shows only 1 GPU
- Worker times out connecting to head

**Diagnosis:**
```bash
# Check Ray head is running
ssh spark1.local "docker exec vllm-spark ray status"

# Check worker logs
ssh spark2.local "docker exec vllm-spark cat /tmp/ray/session_*/logs/raylet.out"
```

**Solutions:**

1. **Verify head is reachable from worker:**
   ```bash
   ssh spark2.local "docker exec vllm-spark python -c \"import socket; socket.create_connection(('192.168.1.1', 6379))\""
   ```

2. **Check RAY_NODE_IP_ADDRESS is set:**
   ```bash
   ssh spark1.local "docker exec vllm-spark env | grep RAY"
   ```

3. **Restart Ray cluster:**
   ```bash
   # Stop on both nodes
   ssh spark1.local "docker exec vllm-spark ray stop"
   ssh spark2.local "docker exec vllm-spark ray stop"

   # Restart head
   ssh spark1.local "docker exec vllm-spark ray start --head \
     --node-ip-address=192.168.1.1 --port=6379 --num-gpus=1"

   # Restart worker
   ssh spark2.local "docker exec vllm-spark ray start \
     --address=192.168.1.1:6379 --node-ip-address=192.168.1.2 --num-gpus=1"
   ```

### Ray Object Store OOM

**Symptoms:**
- "ObjectStoreFullError" in logs
- Ray processes killed

**Solution:** Increase shared memory:
```bash
docker run ... --shm-size=10g ...
```

## vLLM Server Issues

### Server Won't Start

**Symptoms:**
- Server exits immediately
- No response on port 8000

**Diagnosis:**
```bash
# Check logs
ssh spark1.local "docker exec vllm-spark tail -100 /tmp/vllm.log"

# Check if port is in use
ssh spark1.local "netstat -tlnp | grep 8000"
```

**Common causes:**

1. **Ray cluster not ready:**
   ```bash
   # Wait for Ray to show 2 GPUs
   ssh spark1.local "docker exec vllm-spark ray status"
   ```

2. **Previous server still running:**
   ```bash
   ssh spark1.local "docker exec vllm-spark pkill -f 'vllm.entrypoints'"
   ```

3. **Model not found:**
   - Check model name spelling
   - Verify HuggingFace access if model is gated

### OOM During Model Loading

**Symptoms:**
- "CUDA out of memory" errors
- Process killed during loading

**Solutions:**

1. **Reduce GPU memory utilization:**
   ```bash
   --gpu-memory-utilization 0.6  # Instead of 0.7
   ```

2. **Reduce context length:**
   ```bash
   --max-model-len 16384  # Instead of 32768
   ```

3. **Use a smaller quantized model:**
   - GPTQ-Int4 uses ~60GB for 235B model
   - FP8 uses ~235GB (too large for dual Spark)

### Slow First Response

**Expected behavior:** First request after loading takes longer due to:
- CUDA graph capture
- KV cache allocation
- Warmup compilation

**Not a problem unless:** First response takes >5 minutes for a short prompt.

### Model Loading Takes Too Long

**Expected times:**
- Small models (7B-70B): 2-5 minutes
- Large models (200B+): 15-30 minutes

**If loading exceeds these times:**

1. Check RDMA is working (not falling back to TCP)
2. Monitor GPU memory:
   ```bash
   ssh spark1.local "nvidia-smi --query-gpu=memory.used --format=csv -l 5"
   ```

## Docker Issues

### Container Already Exists

**Symptoms:**
- "container name already in use" error

**Solution:**
```bash
ssh spark1.local "docker rm -f vllm-spark"
ssh spark2.local "docker rm -f vllm-spark"
```

### Disk Space Full

**Symptoms:**
- "no space left on device" errors
- Container won't start

**Diagnosis:**
```bash
# Check disk usage
ssh spark1.local "df -h /"

# Check Docker disk usage
ssh spark1.local "docker system df"
```

**Solution:** Clean up Docker:
```bash
# Remove stopped containers
ssh spark1.local "docker container prune -f"

# Remove unused images
ssh spark1.local "docker image prune -a -f"

# Full cleanup (careful!)
ssh spark1.local "docker system prune -a -f"
```

### Container Loses State on Restart

**Expected behavior:** Containers use `sleep infinity` and don't persist state.

**To preserve models:** Mount a volume for HuggingFace cache:
```bash
docker run ... \
  -v /home/user/.cache/huggingface:/root/.cache/huggingface \
  ...
```

## NCCL Issues

### NCCL Timeout

**Symptoms:**
- "NCCL timeout" errors
- Operations hang indefinitely

**Solutions:**

1. **Increase timeout:**
   ```bash
   -e NCCL_TIMEOUT=1800  # 30 minutes
   ```

2. **Check RDMA connectivity (most common cause)**

3. **Verify NCCL environment variables:**
   ```bash
   ssh spark1.local "docker exec vllm-spark env | grep NCCL"
   ```

### NCCL Wrong Interface

**Symptoms:**
- NCCL uses wrong network (e.g., management instead of RDMA)

**Solution:** Set correct interface:
```bash
-e NCCL_SOCKET_IFNAME=enp1s0f1np1
-e NCCL_IB_HCA=rocep1s0f1:1
```

## Performance Issues

### Low Throughput

**Expected:** ~150 tok/s for Qwen3-235B-A22B-GPTQ-Int4

**If significantly lower:**

1. **Check RDMA is working:**
   - Run NCCL test, expect >100 Gbps

2. **Don't use `--enforce-eager`:**
   - Compilation improves performance

3. **Check GPU utilization:**
   ```bash
   ssh spark1.local "nvidia-smi"
   ssh spark2.local "nvidia-smi"
   ```

### High TTFT (Time to First Token)

**Expected:** ~36 seconds for 235B model with 2K input

**If significantly higher:**

1. First request is always slower (warmup)
2. Large `--max-model-len` increases TTFT
3. Check Ray cluster has 2 GPUs

## SSH Issues

### Can't Connect to Sparks

**Check:**
1. mDNS resolution:
   ```bash
   ping spark1.local
   ```

2. SSH key authentication:
   ```bash
   ssh -v spark1.local hostname
   ```

3. SSH config:
   ```bash
   cat ~/.ssh/config
   ```

### SSH Timeout During Long Operations

**Solution:** Add to `~/.ssh/config`:
```
Host spark1.local spark2.local
    ServerAliveInterval 60
    ServerAliveCountMax 10
```

## Getting Help

If these solutions don't resolve your issue:

1. Collect logs:
   ```bash
   ssh spark1.local "docker exec vllm-spark cat /tmp/vllm.log" > vllm.log
   ssh spark1.local "docker exec vllm-spark ray status" > ray_status.txt
   ```

2. Check NVIDIA container runtime:
   ```bash
   ssh spark1.local "nvidia-smi"
   ssh spark1.local "docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi"
   ```

3. Review environment variables in container:
   ```bash
   ssh spark1.local "docker exec vllm-spark env | sort"
   ```
