# Docker & Ray Cluster Setup

This guide covers starting RDMA-enabled containers and configuring a Ray cluster across two DGX Sparks.

## Environment Variables

Create a `.env` file with your configuration (see `.env.example`):

```bash
# Copy and edit
cp .env.example .env
```

Key variables:
```bash
SPARK1_HOST=spark1.local        # Hostname of head node
SPARK2_HOST=spark2.local        # Hostname of worker node
SPARK1_RDMA_IP=192.168.200.3    # RDMA IP of head node
SPARK2_RDMA_IP=192.168.200.13   # RDMA IP of worker node
RDMA_INTERFACE=enp1s0f1np1      # RDMA network interface
CONTAINER_NAME=vllm-spark       # Docker container name
```

## Container Configuration

### Critical Environment Variables

These environment variables are **required** for distributed inference over RDMA:

| Variable | Purpose |
|----------|---------|
| `NCCL_IB_DISABLE=0` | Enable InfiniBand/RoCE |
| `NCCL_IB_HCA=rocep1s0f1:1` | Specify RDMA device |
| `NCCL_IB_GID_INDEX=3` | RoCE GID index |
| `NCCL_SOCKET_IFNAME` | Network interface for NCCL |
| `GLOO_SOCKET_IFNAME` | Network interface for Gloo backend |
| `CUDA_DEVICE_ORDER=PCI_BUS_ID` | Consistent GPU ordering |
| `RAY_OVERRIDE_NODE_IP` | Force Ray to use RDMA IP |
| `VLLM_HOST_IP` | Force vLLM to use RDMA IP |

### Start Containers

**Spark 1 (Head Node):**
```bash
docker run -d --name $CONTAINER_NAME \
  --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=$RDMA_INTERFACE \
  -e NCCL_IB_DISABLE=0 \
  -e NCCL_IB_HCA=rocep1s0f1:1 \
  -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=$RDMA_INTERFACE \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=$SPARK1_RDMA_IP \
  -e RAY_OVERRIDE_NODE_IP=$SPARK1_RDMA_IP \
  -e VLLM_HOST_IP=$SPARK1_RDMA_IP \
  nvcr.io/nvidia/vllm:26.03-py3 sleep infinity
```

**Spark 2 (Worker Node):**
```bash
docker run -d --name $CONTAINER_NAME \
  --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
  --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
  -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
  -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
  -e GLOO_SOCKET_IFNAME=$RDMA_INTERFACE \
  -e NCCL_IB_DISABLE=0 \
  -e NCCL_IB_HCA=rocep1s0f1:1 \
  -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=$RDMA_INTERFACE \
  -e RAY_USE_MULTIPLE_IPS=0 \
  -e RAY_NODE_IP_ADDRESS=$SPARK2_RDMA_IP \
  -e RAY_OVERRIDE_NODE_IP=$SPARK2_RDMA_IP \
  nvcr.io/nvidia/vllm:26.03-py3 sleep infinity
```

### Container Flags Explained

| Flag | Purpose |
|------|---------|
| `--runtime=nvidia --gpus all` | Enable GPU access |
| `--network host` | Use host networking for RDMA |
| `--ipc=host` | Shared memory for multi-process |
| `--shm-size=10g` | Increase shared memory |
| `--privileged` | Required for InfiniBand access |
| `--ulimit memlock=-1` | Unlimited locked memory |
| `-v /dev/infiniband:/dev/infiniband` | Pass through RDMA devices |

## Ray Cluster Setup

### Start Ray Head (Spark 1)

```bash
docker exec $CONTAINER_NAME ray start --head \
  --node-ip-address=$SPARK1_RDMA_IP \
  --port=6379 \
  --dashboard-host=$SPARK1_RDMA_IP \
  --dashboard-port=8265 \
  --num-gpus=1
```

### Start Ray Worker (Spark 2)

```bash
docker exec $CONTAINER_NAME ray start \
  --address=$SPARK1_RDMA_IP:6379 \
  --node-ip-address=$SPARK2_RDMA_IP \
  --num-gpus=1
```

### Verify Cluster

```bash
docker exec $CONTAINER_NAME ray status
```

Expected output:
```
Node status
---------------------------------------------------------------
Active:
 1 node_xxx (head)
 1 node_yyy (worker)

Resources
---------------------------------------------------------------
Total Usage:
 0.0/40.0 CPU
 0.0/2.0 GPU        # <-- Should show 2 GPUs
```

## NCCL Communication Test

Verify GPU-to-GPU communication works over RDMA:

**test_nccl.py:**
```python
import os
import torch
import torch.distributed as dist
import argparse

def test_nccl():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rank', type=int, required=True)
    parser.add_argument('--world_size', type=int, default=2)
    parser.add_argument('--master_addr', type=str, required=True)
    args = parser.parse_args()

    os.environ['RANK'] = str(args.rank)
    os.environ['WORLD_SIZE'] = str(args.world_size)
    os.environ['MASTER_ADDR'] = args.master_addr
    os.environ['MASTER_PORT'] = '29500'

    dist.init_process_group(backend='nccl')

    tensor = torch.ones(10, device='cuda:0') * (args.rank + 1)
    print(f"Rank {args.rank} before: {tensor}")

    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    print(f"Rank {args.rank} after: {tensor}")  # Should be [3, 3, 3, ...]

    dist.destroy_process_group()

if __name__ == "__main__":
    test_nccl()
```

Run on both nodes simultaneously:
```bash
# Spark 1
docker exec $CONTAINER_NAME python test_nccl.py --rank 0 --master_addr 192.168.200.3

# Spark 2
docker exec $CONTAINER_NAME python test_nccl.py --rank 1 --master_addr 192.168.200.3
```

## Shutdown

### Stop Ray
```bash
# On both nodes
docker exec $CONTAINER_NAME ray stop
```

### Stop Containers
```bash
# On both nodes
docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME
```

## Maintenance

### Docker Disk Space

Containers accumulate significant space. Clean up regularly:

```bash
# Check usage
docker system df

# Remove stopped containers
docker container prune

# Full cleanup
docker system prune -a
```

## Next Steps

Continue to your framework of choice:
- [vLLM Inference](frameworks/vllm/)
- [SGLang](frameworks/sglang/) (coming soon)
