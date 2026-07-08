import sounddevice as sd

DEVICE = 26

for fs in [8000, 16000, 22050, 32000, 44100, 48000]:
    try:
        sd.check_input_settings(device=DEVICE, samplerate=fs, channels=1)
        print(f"{fs} Hz: OK")
    except Exception as e:
        print(f"{fs} Hz: NG - {e}")