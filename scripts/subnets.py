"""Task 5: allocate 10.20.0.0/16 largest-first, contiguous, smallest prefix that fits.
Prints the table used in network/subnets.md (and checked by tests/test_network.py)."""
import ipaddress
import math

BLOCK = ipaddress.ip_network("10.20.0.0/16")
NEEDS = [("app", 1000), ("public", 250), ("data", 100), ("management", 20)]


def smallest_prefix(hosts):
    # usable = 2^(32 - prefix) - 2 >= hosts  ->  32 - prefix >= log2(hosts + 2)
    return 32 - math.ceil(math.log2(hosts + 2))


def allocate():
    rows, next_addr = [], BLOCK.network_address
    for name, hosts in sorted(NEEDS, key=lambda x: -x[1]):
        net = ipaddress.ip_network(f"{next_addr}/{smallest_prefix(hosts)}")
        assert net.subnet_of(BLOCK) and net.network_address == next_addr
        rows.append({"name": name, "needed": hosts, "network": str(net.network_address),
                     "prefix": net.prefixlen, "first": str(net.network_address + 1),
                     "last": str(net.broadcast_address - 1), "broadcast": str(net.broadcast_address),
                     "usable": net.num_addresses - 2, "cidr": str(net)})
        next_addr = net.broadcast_address + 1
    return rows


if __name__ == "__main__":
    print("| Subnet | Hosts needed | Network address | Prefix | Usable host range | Broadcast | Usable hosts |")
    print("|---|---|---|---|---|---|---|")
    for r in allocate():
        print(f"| {r['name']} | {r['needed']} | {r['network']} | /{r['prefix']} | "
              f"{r['first']} to {r['last']} | {r['broadcast']} | {r['usable']} |")
