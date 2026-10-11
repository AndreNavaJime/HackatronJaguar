"""Diagnóstico sin cargar modelos grandes para PantheraID 2.0 en Codespaces.

Ejecutar: python diagnostico.py
No instala nada, no modifica archivos y no imprime credenciales.
"""
from importlib.util import find_spec
from pathlib import Path
import shutil
from urllib.error import URLError
from urllib.request import urlopen


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def human_bytes(value):
    try:
        return f"{int(value) / (1024**3):.2f} GiB"
    except (ValueError, TypeError, OverflowError):
        return "no disponible"


def main():
    print("=== PantheraID 2.0 — diagnóstico de Codespaces ===")
    for module in ("fastapi", "PIL", "torch", "torchvision", "cv2", "PytorchWildlife"):
        try:
            available = find_spec(module) is not None
        except (ImportError, ValueError):
            available = False
        print(f"{module}: {'encontrado' if available else 'no encontrado'} (sin cargar)")

    limit = read_text("/sys/fs/cgroup/memory.max")
    current = read_text("/sys/fs/cgroup/memory.current")
    if limit is None:
        print("Límite de RAM del contenedor: no disponible")
    elif limit == "max":
        print("Límite de RAM del contenedor: sin límite explícito (cgroup)")
    else:
        print(f"Límite de RAM del contenedor: {human_bytes(limit)}")
    print(f"RAM en uso del contenedor: {human_bytes(current)}")
    if limit not in (None, "max") and current is not None:
        try:
            print(f"RAM libre aproximada dentro del límite: {human_bytes(max(0, int(limit) - int(current)))}")
        except ValueError:
            pass

    events = read_text("/sys/fs/cgroup/memory.events")
    if events:
        values = dict(line.split() for line in events.splitlines() if len(line.split()) == 2)
        print(f"Eventos OOM reportados: {values.get('oom', 'no disponible')}")
        print(f"Procesos finalizados por OOM: {values.get('oom_kill', 'no disponible')}")
        print("Nota: los contadores OOM son acumulativos; no prueban por sí solos qué solicitud falló.")
    else:
        print("Contadores OOM: no disponibles en este entorno")

    total, used, free = shutil.disk_usage(Path(__file__).resolve().parent)
    print(f"Disco libre: {human_bytes(free)} / {human_bytes(total)}")
    try:
        with urlopen("http://127.0.0.1:8000/api/health", timeout=2) as response:
            print(f"FastAPI puerto 8000: HTTP {response.status} ({response.read(250).decode('utf-8', 'replace')})")
    except (OSError, URLError) as error:
        print(f"FastAPI puerto 8000: no responde ({type(error).__name__})")


if __name__ == "__main__":
    main()
