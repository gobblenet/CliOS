from driver import Slcan


def chasse_au_tresor(port="/dev/cu.usbmodem207B3949534B1", baudrate=500000):
    driver = Slcan(channel=port, baudrate=baudrate)

    if not driver.connect():
        print("❌ Port closed.")
        return

    print("✅ Listening... Gently press the accelerator to vary boost/RPM.")

    # On va mémoriser l'état précédent de chaque trame
    memoire_trames = {}

    try:
        while True:
            frame = driver.read_frame(timeout=0.1)
            if frame:
                id_trame = frame.arbitration_id
                # On convertit les octets en tableau pour comparer facilement
                data_actuelle = list(frame.data)

                # Si on a déjà vu cette trame
                if id_trame in memoire_trames:
                    data_precedente = memoire_trames[id_trame]

                    # On compare octet par octet
                    changements = []
                    for i in range(len(data_actuelle)):
                        if data_actuelle[i] != data_precedente[i]:
                            changements.append(i)

                    # S'il y a un changement, on l'affiche avec des couleurs (si ton terminal le supporte)
                    if changements:
                        hex_data = " ".join([f"{b:02X}" for b in data_actuelle])
                        print(f"Frame [0x{id_trame:03X}] changed! -> {hex_data} (bytes changed: {changements})")

                # On met à jour la mémoire
                memoire_trames[id_trame] = data_actuelle

    except KeyboardInterrupt:
        print("\n🏁 Frame hunter stopped.")
        driver.close()


if __name__ == "__main__":
    chasse_au_tresor()