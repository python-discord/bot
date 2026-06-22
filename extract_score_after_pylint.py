import os
import subprocess

PROJETO = "./bot"
PASTA = "metrics-after-pylint"

os.makedirs(PASTA, exist_ok=True)

# Eu tive que adicionar essas linhas pois o projeto usa emojis e o score não estava sendo mostrado
env_corrigido = os.environ.copy()
env_corrigido["PYTHONIOENCODING"] = "utf-8"
env_corrigido["PYTHONUTF8"] = "1"

resultado = subprocess.run(
    ["pylint", PROJETO, "--score=y"],
    capture_output=True,
    text=True,
    encoding="utf-8",
    env=env_corrigido,
)

caminho_score = os.path.join(PASTA, "pylint_score_depois.txt")
with open(caminho_score, "w", encoding="utf-8") as f:
    for linha in resultado.stdout.splitlines():
        if "Your code has been rated at" in linha:
            f.write(linha + "\n")
            print(linha)

print(f"Score salvo em: {caminho_score}")
