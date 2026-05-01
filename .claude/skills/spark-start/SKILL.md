---
name: spark-start
description: Start DGX Spark containers and Ray cluster for distributed inference
allowed-tools: Bash(ssh *) Bash(docker *) Bash(source *) Read
---

# Start DGX Spark Infrastructure

## Prerequisites

Source the environment configuration:
```bash
source playbooks/dual-dgx-spark-setup/.env
```

## Steps

1. **Start container on Spark 1 (head)**:
   ```bash
   ssh $SPARK1_HOST "docker run -d --name $CONTAINER_NAME \
     --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
     --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
     -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
     -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
     -e GLOO_SOCKET_IFNAME=$RDMA_INTERFACE \
     -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
     -e NCCL_SOCKET_IFNAME=$RDMA_INTERFACE \
     -e RAY_USE_MULTIPLE_IPS=0 \
     -e RAY_NODE_IP_ADDRESS=$SPARK1_RDMA_IP \
     -e RAY_OVERRIDE_NODE_IP=$SPARK1_RDMA_IP \
     -e VLLM_HOST_IP=$SPARK1_RDMA_IP \
     $VLLM_CONTAINER sleep infinity"
   ```

2. **Start container on Spark 2 (worker)**:
   ```bash
   ssh $SPARK2_HOST "docker run -d --name $CONTAINER_NAME \
     --runtime=nvidia --gpus all --network host --ipc=host --shm-size=10g \
     --privileged --ulimit memlock=-1 --ulimit stack=67108864 \
     -v /dev/infiniband:/dev/infiniband -v /sys:/sys:ro \
     -e CUDA_DEVICE_ORDER=PCI_BUS_ID \
     -e GLOO_SOCKET_IFNAME=$RDMA_INTERFACE \
     -e NCCL_IB_DISABLE=0 -e NCCL_IB_HCA=rocep1s0f1:1 -e NCCL_IB_GID_INDEX=3 \
     -e NCCL_SOCKET_IFNAME=$RDMA_INTERFACE \
     -e RAY_USE_MULTIPLE_IPS=0 \
     -e RAY_NODE_IP_ADDRESS=$SPARK2_RDMA_IP \
     -e RAY_OVERRIDE_NODE_IP=$SPARK2_RDMA_IP \
     $VLLM_CONTAINER sleep infinity"
   ```

3. **Start Ray head on Spark 1**:
   ```bash
   ssh $SPARK1_HOST "docker exec $CONTAINER_NAME ray start --head \
     --node-ip-address=$SPARK1_RDMA_IP --port=6379 \
     --dashboard-host=$SPARK1_RDMA_IP --dashboard-port=8265 --num-gpus=1"
   ```

4. **Start Ray worker on Spark 2**:
   ```bash
   ssh $SPARK2_HOST "docker exec $CONTAINER_NAME ray start \
     --address=$SPARK1_RDMA_IP:6379 --node-ip-address=$SPARK2_RDMA_IP --num-gpus=1"
   ```

5. **Verify Ray cluster**:
   ```bash
   ssh $SPARK1_HOST "docker exec $CONTAINER_NAME ray status"
   ```

Report success when Ray shows 2 GPUs available.
