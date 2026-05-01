#!/usr/bin/env python3
"""
NCCL Communication Test for Multi-Node GPU Setup
Tests all-reduce operation across nodes via RDMA

Usage:
  Node 0: python3 test_nccl.py --rank 0 --master_addr <RDMA_IP>
  Node 1: python3 test_nccl.py --rank 1 --master_addr <RDMA_IP>
"""

import os
import torch
import torch.distributed as dist
import argparse
import time

def test_nccl_communication():
    parser = argparse.ArgumentParser(description='Test NCCL communication across nodes')
    parser.add_argument('--rank', type=int, required=True, help='Node rank (0 or 1)')
    parser.add_argument('--world_size', type=int, default=2, help='Total number of nodes')
    parser.add_argument('--master_addr', type=str, required=True, help='Master node RDMA IP')
    parser.add_argument('--master_port', type=str, default='29500', help='Master port')
    parser.add_argument('--interface', type=str, default='enp1s0f1np1', help='NCCL socket interface')
    args = parser.parse_args()

    # Set environment variables
    os.environ['RANK'] = str(args.rank)
    os.environ['WORLD_SIZE'] = str(args.world_size)
    os.environ['MASTER_ADDR'] = args.master_addr
    os.environ['MASTER_PORT'] = args.master_port
    os.environ['NCCL_SOCKET_IFNAME'] = args.interface

    print(f"[Rank {args.rank}] Initializing process group...")
    print(f"[Rank {args.rank}] Master: {args.master_addr}:{args.master_port}")
    print(f"[Rank {args.rank}] NCCL interface: {args.interface}")

    # Initialize process group
    dist.init_process_group(backend='nccl', rank=args.rank, world_size=args.world_size)
    print(f"[Rank {args.rank}] Process group initialized: {dist.get_rank()}/{dist.get_world_size()}")

    # Create test tensor on GPU
    device = torch.device('cuda:0')
    tensor = torch.ones(10, device=device) * (args.rank + 1)
    print(f"[Rank {args.rank}] Before all-reduce: {tensor}")

    # Perform all-reduce
    start_time = time.time()
    dist.all_reduce(tensor, op=dist.ReduceOp.SUM)
    elapsed = time.time() - start_time

    print(f"[Rank {args.rank}] After all-reduce: {tensor}")
    print(f"[Rank {args.rank}] Expected: tensor([3., 3., 3., 3., 3., 3., 3., 3., 3., 3.])")
    print(f"[Rank {args.rank}] All-reduce completed in {elapsed*1000:.2f} ms")

    # Verify result
    expected = torch.ones(10, device=device) * 3  # 1 + 2 = 3
    if torch.allclose(tensor, expected):
        print(f"[Rank {args.rank}] SUCCESS: All-reduce result is correct!")
    else:
        print(f"[Rank {args.rank}] FAILED: Result mismatch!")

    # Cleanup
    dist.destroy_process_group()
    print(f"[Rank {args.rank}] Test completed successfully!")

if __name__ == "__main__":
    test_nccl_communication()
