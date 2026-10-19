import asyncio
from bleak import BleakScanner

async def main():
    print("Searching for Bluetooth devices...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        # Filtre optionnel pour éviter d'afficher les télés des voisins
        if d.name and d.name != "Unknown":
            print(f"Adresse: {d.address} | Nom: {d.name}")

asyncio.run(main())