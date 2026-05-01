# Utilities

Diagnostic and testing utilities for dual DGX Spark setup.

## Scripts

### test_nccl.py

Tests NCCL GPU-to-GPU communication over RDMA between two nodes.

**Usage:**
```bash
# On Node 0 (run first)
python3 test_nccl.py --rank 0 --master_addr 192.168.200.3

# On Node 1
python3 test_nccl.py --rank 1 --master_addr 192.168.200.3
```

**Expected output:**
```
[Rank 0] Before all-reduce: tensor([1., 1., 1., ...])
[Rank 0] After all-reduce: tensor([3., 3., 3., ...])
[Rank 0] SUCCESS: All-reduce result is correct!
```

### dual_port_monitor.py

Real-time monitoring of RDMA network interfaces. Shows throughput on both ConnectX-7 ports.

**Usage:**
```bash
python3 dual_port_monitor.py
```

**Features:**
- Auto-detects network interfaces and RDMA devices
- Shows real-time Gbps throughput per interface
- Aggregates total bandwidth across both ports
- Color-coded activity indicators

**Sample output:**
```
====================================================================
           DUAL-PORT RDMA NETWORK MONITOR
====================================================================

NETWORK INTERFACE STATISTICS:
Interface       RX Rate      TX Rate      Total RX     Total TX
------------------------------------------------------------------------
enp1s0f0np0        0.000 Gbps    0.000 Gbps    1.23 GB      2.45 GB
enp1s0f1np1       98.234 Gbps   98.456 Gbps  456.78 GB    567.89 GB
------------------------------------------------------------------------
TOTAL AGGREGATE:  98.234 Gbps   98.456 Gbps

HIGH ACTIVITY - Multi-rail likely active!
```

## Running Inside Containers

Copy utilities into the container:
```bash
docker cp utilities/test_nccl.py vllm-spark:/workspace/
docker exec vllm-spark python3 /workspace/test_nccl.py --rank 0 --master_addr 192.168.200.3
```

Or mount the directory:
```bash
docker run ... -v $(pwd)/utilities:/workspace/utilities ...
```
