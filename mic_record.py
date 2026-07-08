import sounddevice as sd
import soundfile as sf

DEVICE = 18
FS = 32000
SECONDS = 5

print("5秒録音します。話してください。")

recording = sd.rec(
    int(SECONDS * FS),
    samplerate=FS,
    channels=1,
    dtype="int16",
    device=DEVICE
)

sd.wait()

sf.write("test.wav", recording, FS)

print("録音終了：test.wav を保存しました。")