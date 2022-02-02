"""Detects temperature of cpu and toggle light if drastic decrease"""
import time
import csv
from toggle import toggle

temps = []
TIMESTEP = 0.5
THRESHOLD = 1.5


def average(items, decimals=None):
    """Calculate average of list and round"""
    if not items:
        return 0
    result = sum(items) / len(items)
    return round(result, decimals) if decimals else result


while True:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = float(f.read())
            tempC = temp / 1000
            part = temps[-5:]  # Slice to calculate average on
            avg = average(part, decimals=1)
            if avg - tempC > THRESHOLD:
                print()
                print("Touching sensor!!!")
                print(part, tempC)
                toggle()
            temps.append(tempC)
            print(f"{tempC} average: {avg}", end="\r")
            time.sleep(TIMESTEP)
    except KeyboardInterrupt as err:
        print()
        print(temps)
        with open("templog.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=";")
            writer.writerow(["time", "temp"])
            for index, row in enumerate(temps):
                writer.writerow([TIMESTEP * index, row])
        raise err
