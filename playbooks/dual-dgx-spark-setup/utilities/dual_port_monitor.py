#!/usr/bin/env python3
"""
Dual-Port Network Monitor for RDMA Interfaces
Monitors both ConnectX ports simultaneously to verify multi-rail usage

Usage: python3 dual_port_monitor.py
"""

import time
import subprocess
import signal
import sys
from datetime import datetime
import os

class DualPortMonitor:
    def __init__(self, interfaces=None, rdma_devices=None):
        # Auto-detect or use provided interfaces
        self.interfaces = interfaces or ['enp1s0f0np0', 'enp1s0f1np1']
        self.rdma_devices = rdma_devices or ['rocep1s0f0', 'rocep1s0f1']
        self.running = True

        # Previous stats for calculating rates
        self.prev_stats = {}

        # Terminal colors
        self.CYAN = '\033[96m'
        self.GREEN = '\033[92m'
        self.YELLOW = '\033[93m'
        self.RED = '\033[91m'
        self.BOLD = '\033[1m'
        self.ENDC = '\033[0m'

        # Setup signal handler
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        print(f"\n{self.YELLOW}Stopping monitor...{self.ENDC}")
        self.running = False

    def get_interface_stats(self, interface):
        """Get network interface statistics"""
        try:
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()

            for line in lines:
                if interface in line:
                    fields = line.split()
                    return {
                        'rx_bytes': int(fields[1]),
                        'rx_packets': int(fields[2]),
                        'tx_bytes': int(fields[9]),
                        'tx_packets': int(fields[10])
                    }
            return None
        except Exception:
            return None

    def get_rdma_stats(self, device):
        """Get RDMA device statistics"""
        try:
            base_path = f"/sys/class/infiniband/{device}/ports/1/counters"
            stats = {}

            counters = [
                'port_rcv_data', 'port_xmit_data',
                'port_rcv_packets', 'port_xmit_packets'
            ]

            for counter in counters:
                try:
                    with open(f"{base_path}/{counter}", 'r') as f:
                        stats[counter] = int(f.read().strip())
                except:
                    stats[counter] = 0

            return stats
        except Exception:
            return None

    def bytes_to_gbps(self, bytes_val, time_diff):
        """Convert bytes per time_diff to Gbps"""
        if time_diff <= 0:
            return 0
        bits_per_sec = (bytes_val * 8) / time_diff
        return bits_per_sec / (1024**3)

    def format_bytes(self, bytes_val):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def print_header(self):
        """Print monitoring header"""
        print(f"{self.BOLD}{self.CYAN}")
        print("="*100)
        print("           DUAL-PORT RDMA NETWORK MONITOR")
        print("="*100)
        print(f"{self.ENDC}")
        print(f"{self.BOLD}Monitoring interfaces: {', '.join(self.interfaces)}{self.ENDC}")
        print(f"{self.BOLD}Monitoring RDMA devices: {', '.join(self.rdma_devices)}{self.ENDC}")
        print()

    def print_stats(self, current_stats, time_diff):
        """Print current statistics"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        os.system('clear')
        self.print_header()

        print(f"{self.BOLD}Timestamp: {timestamp} (Δt: {time_diff:.1f}s){self.ENDC}")
        print()

        total_rx_gbps = 0
        total_tx_gbps = 0

        # Network Interface Stats
        print(f"{self.BOLD}{self.GREEN}NETWORK INTERFACE STATISTICS:{self.ENDC}")
        print(f"{'Interface':<15} {'RX Rate':<12} {'TX Rate':<12} {'Total RX':<12} {'Total TX':<12}")
        print("-" * 80)

        for interface in self.interfaces:
            stats = current_stats.get(f'net_{interface}')
            prev = self.prev_stats.get(f'net_{interface}', {})

            if stats and prev:
                rx_rate = self.bytes_to_gbps(stats['rx_bytes'] - prev['rx_bytes'], time_diff)
                tx_rate = self.bytes_to_gbps(stats['tx_bytes'] - prev['tx_bytes'], time_diff)
                total_rx_gbps += rx_rate
                total_tx_gbps += tx_rate

                color = self.GREEN if (rx_rate > 0.1 or tx_rate > 0.1) else ""
                print(f"{color}{interface:<15} {rx_rate:>8.3f} Gbps {tx_rate:>8.3f} Gbps "
                      f"{self.format_bytes(stats['rx_bytes']):>10} {self.format_bytes(stats['tx_bytes']):>10}{self.ENDC}")

        print("-" * 80)
        print(f"{self.BOLD}TOTAL AGGREGATE: {total_rx_gbps:>8.3f} Gbps {total_tx_gbps:>8.3f} Gbps{self.ENDC}")
        print()

        # RDMA Device Stats
        print(f"{self.BOLD}{self.CYAN}RDMA DEVICE STATISTICS:{self.ENDC}")
        print(f"{'Device':<15} {'RX Rate':<12} {'TX Rate':<12} {'RX Packets':<12} {'TX Packets':<12}")
        print("-" * 80)

        total_rdma_rx = 0
        total_rdma_tx = 0

        for device in self.rdma_devices:
            stats = current_stats.get(f'rdma_{device}')
            prev = self.prev_stats.get(f'rdma_{device}', {})

            if stats and prev:
                rx_bytes_diff = (stats['port_rcv_data'] - prev['port_rcv_data']) * 4
                tx_bytes_diff = (stats['port_xmit_data'] - prev['port_xmit_data']) * 4

                rx_rate = self.bytes_to_gbps(rx_bytes_diff, time_diff)
                tx_rate = self.bytes_to_gbps(tx_bytes_diff, time_diff)

                rx_pkt_rate = (stats['port_rcv_packets'] - prev['port_rcv_packets']) / time_diff if time_diff > 0 else 0
                tx_pkt_rate = (stats['port_xmit_packets'] - prev['port_xmit_packets']) / time_diff if time_diff > 0 else 0

                total_rdma_rx += rx_rate
                total_rdma_tx += tx_rate

                color = self.GREEN if (rx_rate > 0.1 or tx_rate > 0.1) else ""
                print(f"{color}{device:<15} {rx_rate:>8.3f} Gbps {tx_rate:>8.3f} Gbps "
                      f"{rx_pkt_rate:>9.1f} pps {tx_pkt_rate:>9.1f} pps{self.ENDC}")

        print("-" * 80)
        print(f"{self.BOLD}RDMA TOTAL:     {total_rdma_rx:>8.3f} Gbps {total_rdma_tx:>8.3f} Gbps{self.ENDC}")
        print()

        if total_rx_gbps > 1 or total_tx_gbps > 1:
            print(f"{self.BOLD}{self.GREEN}HIGH ACTIVITY - Multi-rail likely active!{self.ENDC}")
        elif total_rx_gbps > 0.1 or total_tx_gbps > 0.1:
            print(f"{self.YELLOW}Moderate activity detected{self.ENDC}")
        else:
            print(f"{self.RED}Low/no activity{self.ENDC}")

        print(f"\n{self.BOLD}Press Ctrl+C to stop monitoring{self.ENDC}")

    def collect_stats(self):
        """Collect all statistics"""
        stats = {}

        for interface in self.interfaces:
            net_stats = self.get_interface_stats(interface)
            if net_stats:
                stats[f'net_{interface}'] = net_stats

        for device in self.rdma_devices:
            rdma_stats = self.get_rdma_stats(device)
            if rdma_stats:
                stats[f'rdma_{device}'] = rdma_stats

        return stats

    def run(self):
        """Main monitoring loop"""
        self.print_header()
        print("Initializing monitoring... (collecting baseline)")

        self.prev_stats = self.collect_stats()
        time.sleep(2)

        while self.running:
            try:
                current_stats = self.collect_stats()

                if self.prev_stats:
                    self.print_stats(current_stats, 2.0)

                self.prev_stats = current_stats
                time.sleep(2)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)

        print(f"\n{self.GREEN}Monitoring stopped.{self.ENDC}")

def main():
    print("Auto-detecting network interfaces and RDMA devices...")

    interfaces = []
    rdma_devices = []

    try:
        result = subprocess.run(['ip', 'link'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'enp1s0f' in line and '@' not in line:
                interface = line.split(':')[1].strip()
                interfaces.append(interface)
    except:
        pass

    try:
        result = subprocess.run(['ls', '/sys/class/infiniband'], capture_output=True, text=True)
        for device in result.stdout.split():
            if 'roce' in device:
                rdma_devices.append(device.strip())
    except:
        pass

    if not interfaces or not rdma_devices:
        print("Could not auto-detect interfaces. Using defaults.")
        interfaces = ['enp1s0f0np0', 'enp1s0f1np1']
        rdma_devices = ['rocep1s0f0', 'rocep1s0f1']

    print(f"Detected interfaces: {interfaces}")
    print(f"Detected RDMA devices: {rdma_devices}")
    print()

    monitor = DualPortMonitor(interfaces=interfaces, rdma_devices=rdma_devices)
    monitor.run()

if __name__ == "__main__":
    main()
