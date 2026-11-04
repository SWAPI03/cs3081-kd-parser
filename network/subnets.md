# Task 5: Subnetting and network access control

## 1. Subnet plan for 10.20.0.0/16

Method (as required): allocate from the largest requirement to the smallest, start at
10.20.0.0, place each subnet right after the previous one, and use the smallest prefix that
fits. Usable hosts = 2^(32 - prefix) - 2 (the network and broadcast addresses are not usable).
`python scripts/subnets.py` prints the same table; `tests/test_network.py` checks it.

| Subnet | Hosts needed | Network address | Prefix | Usable host range | Broadcast | Usable hosts |
|---|---|---|---|---|---|---|
| app | 1000 | 10.20.0.0 | /22 | 10.20.0.1 to 10.20.3.254 | 10.20.3.255 | 1022 |
| public | 250 | 10.20.4.0 | /24 | 10.20.4.1 to 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | 10.20.5.0 | /25 | 10.20.5.1 to 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | 10.20.5.128 | /27 | 10.20.5.129 to 10.20.5.158 | 10.20.5.159 | 30 |

### Working
| Subnet | Hosts needed | Too small | Chosen | Usable hosts | Block size | Next free address |
|---|---|---|---|---|---|---|
| app | 1,000 | /23 = 2^9 - 2 = 510 | /22 = 2^10 - 2 | 1,022 | 1,024 | 10.20.4.0 |
| public | 250 | /25 = 2^7 - 2 = 126 | /24 = 2^8 - 2 | 254 | 256 | 10.20.5.0 |
| data | 100 | /26 = 2^6 - 2 = 62 | /25 = 2^7 - 2 | 126 | 128 | 10.20.5.128 |
| management | 20 | /28 = 2^4 - 2 = 14 | /27 = 2^5 - 2 | 30 | 32 | 10.20.5.160 |

Each network address is the previous subnet's broadcast address + 1, so there are no gaps:
10.20.3.255 + 1 = 10.20.4.0, 10.20.4.255 + 1 = 10.20.5.0, 10.20.5.127 + 1 = 10.20.5.128.
Every network address is also aligned to its block size (for example 10.20.5.128 is a multiple of 32
inside the /24), which a valid subnet requires.

## 2. NACL for the public subnet (network/nacl.json)

Inbound (the abusive-range deny is checked first):
| Rule | Protocol | Ports | Source | Action | Why |
|---|---|---|---|---|---|
| 100 | all | all | 198.51.100.0/24 | deny | block the abusive range on every port, web ports included |
| 200 | tcp | 80 | 0.0.0.0/0 | allow | HTTP from anywhere |
| 210 | tcp | 443 | 0.0.0.0/0 | allow | HTTPS from anywhere |
| 300 | tcp | 22 | 10.20.5.128/27 | allow | SSH only from the management subnet |
| 400 | tcp | 1024 to 65535 | 10.20.0.0/22 | allow | replies from the app subnet arrive on the load balancer's ephemeral ports |
| (default) | | | | deny | nothing else |

Outbound:
| Rule | Protocol | Ports | Destination | Action | Why |
|---|---|---|---|---|---|
| 100 | tcp | 8000 | 10.20.0.0/22 | allow | the load balancer forwards /parse to the app subnet |
| 200 | tcp | 1024 to 65535 | 0.0.0.0/0 | allow | replies to clients go to their ephemeral ports |
| (default) | | | | deny | nothing else |

Check: `python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check`
gives 6 / 6 (`results/task5_nacl_check.txt`).

## 3. Why a stateless NACL needs reply rules, and why rule order matters

A NACL is stateless: it does not remember that a connection was opened, so every packet is
judged on its own, including replies. When a client connects to the load balancer on port 443,
the reply leaves the public subnet towards the client's ephemeral port (1024 to 65535). Without
outbound rule 200 that reply matches nothing and is dropped by the default deny, so the
connection fails even though the request was allowed in. The same applies the other way: the
answer from the app subnet comes back to the load balancer's ephemeral port and needs inbound
rule 400. A stateful firewall (such as a security group) would allow these replies automatically.

Rules are checked from the lowest number upward and the first match decides. A packet from
198.51.100.9 to port 443 matches both the deny (100) and the HTTPS allow (210). Because the
deny has the lower number it is checked first and the packet is dropped. If the deny were
numbered, say, 250, the allow at 210 would match first and the abusive range could reach the
web ports. So a deny only works if its number is lower than every allow it must override.

Limitation: rule 200 allows any destination port from 1024 to 65535, so it also permits outbound
traffic to port 8000 outside the app subnet. A stateless rule cannot tell a reply from a new
connection; a stateful security group on the instances would close that gap.
