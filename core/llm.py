import subprocess


def run_llama(model, prompt, n=200, context_size=4096, timeout=60):
    try:
        result = subprocess.run(
            [
                "llama-cli", "-hf", model, "-st", "-p", prompt,
                "-n", str(n), "-c", str(context_size), "--no-display-prompt"
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "", 124, "llama-cli timed out"
    except FileNotFoundError:
        return "", 127, "llama-cli was not found in PATH"
    except Exception as exc:
        return "", 1, str(exc)

    lines = [
        line for line in result.stdout.strip().splitlines()
        if not line.startswith("[ Prompt:") and not line.startswith("[ Generation:")
    ]
    output = "\n".join(lines).strip()
    if not output:
        return "", result.returncode, result.stderr
    return output, result.returncode, result.stderr
