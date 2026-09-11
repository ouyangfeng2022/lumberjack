# Datacenter Inventory

Current allocation across the three regions we operate.

## Racks

| Rack | Region | Row | Units used | Units free | Power draw | Uplink |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| R-001 | us-east | 1 | 38 | 4 | 9.2 kW | 2 × 100G |
| R-002 | us-east | 1 | 40 | 2 | 9.8 kW | 2 × 100G |
| R-003 | us-east | 2 | 35 | 7 | 8.4 kW | 2 × 100G |
| R-004 | us-east | 3 | 30 | 12 | 7.1 kW | 1 × 100G |
| R-101 | eu-west | 1 | 41 | 1 | 10.1 kW | 2 × 100G |
| R-102 | eu-west | 2 | 39 | 3 | 9.5 kW | 2 × 100G |
| R-201 | ap-south | 1 | 36 | 6 | 8.8 kW | 2 × 40G |
| R-202 | ap-south | 1 | 28 | 14 | 6.9 kW | 1 × 40G |

## Spares

| Part | On hand | Reserved | Reorder point | Lead time |
| --- | ---: | ---: | ---: | ---: |
| 32G DIMM | 48 | 12 | 24 | 9 days |
| 1.9T NVMe | 22 | 6 | 12 | 14 days |
| 25G SFP28 | 60 | 20 | 30 | 5 days |
| 100G QSFP28 | 8 | 4 | 6 | 21 days |
| PSU 800W | 15 | 5 | 8 | 11 days |

## Notes

R-004 and R-202 are scheduled for a switch refresh next quarter. Their
single-uplink state is tracked as a known risk in the capacity plan.
