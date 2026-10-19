"""Synthetic transport network and disruption scenarios for the RouteRescue PoC.

All data here is SIMULATED. Times are "HH:MM" on the travel date; fares in INR.
"""

# Each leg is one bookable service segment.
# road=True marks services that use the Mumbai-Pune Expressway (affected by a road closure).
LEGS = [
    # Direct trains Pune -> Mumbai
    {"service_id": "12127", "name": "Intercity Express", "mode": "train", "operator": "Indian Railways",
     "from": "Pune", "to": "Mumbai", "depart": "06:15", "arrive": "09:30", "fare": 185, "road": False},
    {"service_id": "12123", "name": "Deccan Queen", "mode": "train", "operator": "Indian Railways",
     "from": "Pune", "to": "Mumbai", "depart": "07:15", "arrive": "10:25", "fare": 210, "road": False},
    {"service_id": "11008", "name": "Deccan Express", "mode": "train", "operator": "Indian Railways",
     "from": "Pune", "to": "Mumbai", "depart": "07:00", "arrive": "11:05", "fare": 160, "road": False},
    # Buses Pune -> Mumbai
    {"service_id": "SHV-01", "name": "Shivneri AC Bus", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Mumbai", "depart": "06:30", "arrive": "09:45", "fare": 525, "road": True},
    {"service_id": "ASD-07", "name": "Asiad Bus", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Mumbai", "depart": "07:30", "arrive": "11:00", "fare": 290, "road": True},
    # Cab
    {"service_id": "CAB-PM", "name": "Outstation Cab", "mode": "cab", "operator": "Cab aggregator",
     "from": "Pune", "to": "Mumbai", "depart": "06:30", "arrive": "09:40", "fare": 3200, "road": True},
    # Via Lonavala
    {"service_id": "LOC-PL1", "name": "Pune-Lonavala Local", "mode": "train", "operator": "Central Railway",
     "from": "Pune", "to": "Lonavala", "depart": "06:40", "arrive": "08:00", "fare": 25, "road": False},
    {"service_id": "BUS-PL", "name": "Lonavala Ordinary Bus", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Lonavala", "depart": "07:00", "arrive": "08:15", "fare": 90, "road": False},
    {"service_id": "17317", "name": "Lonavala-Mumbai Passenger", "mode": "train", "operator": "Indian Railways",
     "from": "Lonavala", "to": "Mumbai", "depart": "08:05", "arrive": "10:40", "fare": 110, "road": False},
    {"service_id": "11010", "name": "Sinhagad Express", "mode": "train", "operator": "Indian Railways",
     "from": "Lonavala", "to": "Mumbai", "depart": "08:30", "arrive": "10:35", "fare": 130, "road": False},
    # Via Thane
    {"service_id": "BUS-PT", "name": "Pune-Thane Bus", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Thane", "depart": "06:45", "arrive": "10:00", "fare": 450, "road": True},
    {"service_id": "LOC-TM", "name": "Thane-CSMT Fast Local", "mode": "train", "operator": "Central Railway",
     "from": "Thane", "to": "Mumbai", "depart": "10:15", "arrive": "10:55", "fare": 30, "road": False},
    {"service_id": "MET-TM", "name": "Thane-Mumbai Metro Link", "mode": "metro", "operator": "MMRDA",
     "from": "Thane", "to": "Mumbai", "depart": "10:05", "arrive": "10:50", "fare": 60, "road": False},
    # Pune -> Nashik (second corridor)
    {"service_id": "SHV-NK", "name": "Shivneri Nashik", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Nashik", "depart": "07:00", "arrive": "12:30", "fare": 610, "road": False},
    {"service_id": "BUS-PNK", "name": "Pune-Nashik Ordinary", "mode": "bus", "operator": "MSRTC",
     "from": "Pune", "to": "Nashik", "depart": "06:30", "arrive": "12:45", "fare": 380, "road": False},
    {"service_id": "12117", "name": "Panchavati Express", "mode": "train", "operator": "Indian Railways",
     "from": "Mumbai", "to": "Nashik", "depart": "11:15", "arrive": "14:20", "fare": 175, "road": False},
    {"service_id": "CAB-PN", "name": "Outstation Cab Nashik", "mode": "cab", "operator": "Cab aggregator",
     "from": "Pune", "to": "Nashik", "depart": "06:30", "arrive": "11:30", "fare": 4100, "road": False},
]

CITIES = sorted({leg["from"] for leg in LEGS} | {leg["to"] for leg in LEGS})

# Preset demo scenarios: each pre-fills the input form.
SCENARIOS = {
    "A: Simple cancellation": {
        "origin": "Pune", "destination": "Mumbai", "start": "06:00", "budget": 1000,
        "mode": "train", "priority": "Balanced", "deadline": None,
        "disruption": "Train 12127 Intercity Express is cancelled",
    },
    "B: Tight budget": {
        "origin": "Pune", "destination": "Mumbai", "start": "06:00", "budget": 200,
        "mode": "any", "priority": "Cheapest", "deadline": None,
        "disruption": "Train 12127 cancelled",
    },
    "C: Missed connection": {
        "origin": "Pune", "destination": "Mumbai", "start": "06:30", "budget": 400,
        "mode": "train", "priority": "Fastest", "deadline": None,
        "disruption": "Local LOC-PL1 delayed by 30 min",
    },
    "D: No compliant route": {
        "origin": "Pune", "destination": "Mumbai", "start": "06:00", "budget": 1000,
        "mode": "any", "priority": "Fastest", "deadline": "10:00",
        "disruption": "Train 12127 cancelled and expressway closed",
    },
}
