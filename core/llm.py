import subprocess


def run_llama(model, prompt, n=200, context_size=4096):
    result = subprocess.run(
        ["llama-cli", "-hf", model, "-st", "-p", prompt, "-n", str(n), "-c", str(context_size), "--no-display-prompt"],
        capture_output=True,
        text=True
    )
    lines = [line for line in result.stdout.strip().splitlines() if not line.startswith("[ Prompt:") and not line.startswith("[ Generation:")]
    output = "\n".join(lines).strip()
    if not output:
        return "", result.returncode, result.stderr
    return output, result.returncode, result.stderr
