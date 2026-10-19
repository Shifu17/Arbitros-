"""Revisa el código de la interfaz en busca de errores que las pruebas de humo no detectan."""

import ast
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "src" / "arbitros" / "ui"


def test_ninguna_lambda_llama_funciones_async():
    """`on_click=lambda _: self.algo_async()` crea una corrutina que nadie espera: el botón no hace nada.

    (Así falló el botón «Subir» de Cédulas.) Usa la función async directamente como manejador
    o una función async que la espere.
    """
    problemas = []
    for archivo in UI.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        asincronas = {n.name for n in ast.walk(arbol) if isinstance(n, ast.AsyncFunctionDef)}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Lambda) and isinstance(n.body, ast.Call):
                f = n.body.func
                nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
                if nombre in asincronas:
                    problemas.append(f"{archivo.name}:{n.lineno} -> {nombre}()")
    assert not problemas, "Lambdas que llaman funciones async: " + ", ".join(problemas)
