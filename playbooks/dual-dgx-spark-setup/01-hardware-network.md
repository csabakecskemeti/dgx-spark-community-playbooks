# Hardware & Network Setup

## Hardware Overview

| Device | Role | GPU | NIC |
|--------|------|-----|-----|
| Spark 1 | Head Node | Grace Blackwell GB10 (128GB) | ConnectX-7 200GbE |
| Spark 2 | Worker Node | Grace Blackwell GB10 (128GB) | ConnectX-7 200GbE |

## Network Topology

Direct QSFP cable connection between the two Sparks (no switch required):

```
┌─────────────┐                           ┌─────────────┐
│  Spark 1    │                           │  Spark 2    │
│             │                           │             │
│ enp1s0f1np1 │◄──── 200Gbps QSFP ───────►│ enp1s0f1np1 │
│ 192.168.1.1 │                           │ 192.168.1.2 │
└─────────────┘                           └─────────────┘
```

### IP Addressing Scheme

Use a dedicated subnet for RDMA traffic (e.g., `192.168.200.0/24`):

| Device | RDMA Interface | IP Address |
|--------|---------------|------------|
| Spark 1 | enp1s0f1np1 | 192.168.1.1 |
| Spark 2 | enp1s0f1np1 | 192.168.1.2 |

**Tip:** Using a "+10 offset" pattern makes it easy to identify which Spark an IP belongs to.

## Interface Mapping

DGX Spark has multiple ConnectX-7 ports. Identify the correct interface:

```bash
ibdev2netdev
```

Example output:
```
rocep1s0f0 port 1 ==> enp1s0f0np0
rocep1s0f1 port 1 ==> enp1s0f1np1    # <-- Use this for Spark-to-Spark
roceP2p1s0f0 port 1 ==> enP2p1s0f0np0
roceP2p1s0f1 port 1 ==> enP2p1s0f1np1
```

## Prerequisites

### Install RDMA Packages

```bash
sudo apt update
sudo apt install -y \
  infiniband-diags \
  rdma-core \
  ibverbs-utils \
  mstflint \
  perftest \
  ethtool
```

### Install NVIDIA Container Toolkit

> **Note:** NVIDIA Container Toolkit is NOT pre-installed on DGX Spark.

```bash
# Add NVIDIA container repo
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Install
sudo apt update
sudo apt install -y nvidia-container-toolkit

# Configure Docker runtime
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify:
```bash
docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Add User to Docker Group

```bash
sudo usermod -aG docker $USER
newgrp docker
```

## Network Configuration

### Netplan Configuration

Create `/etc/netplan/99-rdma.yaml` on each Spark:

**Spark 1:**
```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0f1np1:
      addresses:
        - 192.168.200.3/24
      mtu: 9000
      dhcp4: false
```

**Spark 2:**
```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    enp1s0f1np1:
      addresses:
        - 192.168.200.13/24
      mtu: 9000
      dhcp4: false
```

Apply:
```bash
sudo chmod 600 /etc/netplan/99-rdma.yaml
sudo netplan apply
```

### SSH Passwordless Access

Generate keys (if needed):
```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
```

Copy keys between nodes:
```bash
# On Spark 1
ssh-copy-id user@192.168.200.13

# On Spark 2
ssh-copy-id user@192.168.200.3
```

## Verification

### Check RDMA Stack

```bash
lsmod | grep mlx5
ibv_devinfo
ibdev2netdev
```

### Check Link Speed

```bash
ethtool enp1s0f1np1 | grep -i speed
# Expected: Speed: 200000Mb/s
```

### Test Connectivity

```bash
ping 192.168.200.3   # from Spark 2
ping 192.168.200.13  # from Spark 1
```

### RDMA Bandwidth Test

**Spark 1 (server):**
```bash
ib_send_bw -d rocep1s0f1 -b
```

**Spark 2 (client):**
```bash
ib_send_bw -d rocep1s0f1 -b 192.168.200.3
```

**Expected result:** ~200 Gbps bidirectional (25,000+ MB/sec)

## Hardware Notes

### PCIe x4 Limitation

The ConnectX-7 is connected via PCIe Gen5 x4, which limits:
- **Unidirectional:** ~100 Gbps
- **Bidirectional:** ~200 Gbps (full utilization)

This is not a problem for distributed training/inference since NCCL operations are bidirectional.

### Memory Architecture

DGX Spark uses unified memory - the 128GB is shared between CPU and GPU. When running large models:
- Use `--gpu-memory-utilization 0.7` to leave headroom
- Monitor with `nvidia-smi` during model loading

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `netplan apply` hangs | DHCP timeout on other interface | Add `optional: true` to DHCP interfaces |
| Hostname `.local` not resolving | Avahi conflict | `sudo systemctl restart avahi-daemon` |
| Low bandwidth | Wrong interface | Verify with `ibdev2netdev`, use `rocep1s0f1` |

## Next Steps

Continue to [02-docker-ray-setup.md](02-docker-ray-setup.md) for container and Ray cluster configuration.
