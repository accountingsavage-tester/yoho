import subprocess


def speak(text):
    subprocess.run(["termux-tts-speak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def listen():
    result = subprocess.run(["termux-speech-to-text"], capture_output=True, text=True)
    return result.stdout.strip()
