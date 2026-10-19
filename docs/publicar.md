# Cómo publicar una versión nueva

La app instalada busca actualizaciones al abrirse en el repositorio **público** de GitHub
configurado en `src/arbitros/config.py` → `REPO_ACTUALIZACIONES`. Puede ser un repositorio
que solo tenga los instaladores (el código puede quedarse privado): GitHub solo deja
descargar releases sin contraseña desde repositorios públicos.

## Una sola vez

> Ya hecho en la computadora de desarrollo (Inno Setup, GitHub CLI con la cuenta Shifu17 y el
> repositorio público `Shifu17/arbitros-releases`). Solo repetir en otra computadora.

1. Instalar herramientas:
   ```powershell
   winget install JRSoftware.InnoSetup
   winget install GitHub.cli
   ```
2. Iniciar sesión en GitHub: `gh auth login`
3. Crear el repositorio público de instaladores (si no existe), p. ej.:
   `gh repo create arbitros-releases --public --description "Instaladores de Árbitros"`

## Cada versión

1. Subir el número en **ambos**: `src/arbitros/__init__.py` (`__version__`) y `pyproject.toml`.
2. Hacer commit de los cambios.
3. Publicar:
   ```powershell
   .\packaging\publicar.ps1 -Notas "- Novedad 1`n- Corrección 2"
   ```
   Esto corre las pruebas, construye `dist\Arbitros-<versión>-instalador.exe` y su `.sha256`,
   y crea el release `v<versión>` con ambos archivos.

Las computadoras con la app instalada verán al abrirla: *"Nueva versión X disponible"* →
**Actualizar ahora** descarga, verifica (SHA-256), respalda los datos, instala en silencio y
vuelve a abrir la app.

## Solo construir (sin publicar)

```powershell
.\packaging\construir.ps1                 # app + instalador en dist\
.\packaging\construir.ps1 -SinInstalador  # solo la app en dist\Arbitros\ (no requiere Inno Setup)
```

## Notas

- El instalador es por usuario (`%LOCALAPPDATA%\Programs\Arbitros`), sin permisos de administrador.
- Los datos viven en `%APPDATA%\Arbitros` y nunca los toca el instalador ni el desinstalador.
- El ejecutable no está firmado digitalmente: la primera vez Windows SmartScreen puede mostrar
  "Windows protegió tu PC" → *Más información* → *Ejecutar de todas formas*. Con un certificado
  de firma de código esto desaparece.

- El README público del repositorio de instaladores se edita en `docs/README_instalacion.md`
  (su imagen `logo.png` está en la raíz de ese repositorio).
