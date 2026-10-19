# Árbitros — Requisitos acordados

Aplicación de escritorio para Windows que centraliza la administración de árbitros de fútbol:
disponibilidad semanal, ligas y torneos, jornadas y partidos, roles para WhatsApp, cédulas y pagos.
La usa **una sola persona en una computadora**; los datos se guardan en **SQLite local**
y la app funciona sin internet (salvo buscar actualizaciones y abrir WhatsApp).

## Módulos

### 1. Acceso
- Usuario y contraseña. Roles: **Administrador** (todo) y **Consulta** (solo ver).
- **Clave de recuperación** generada al crear el primer administrador; permite restablecer la contraseña.

### 2. Árbitros
- Alta rápida: nombre, apodo, teléfono (WhatsApp), categoría/nivel, activo/inactivo, notas.
- No existe un listado previo: no se importa desde Excel.
- Historial de asignaciones y pagos (cuando existan esos módulos).

### 3. Ligas y torneos
- Dos tipos: **liga** (temporada con jornadas) y **torneo corto** (1 a 3 días, días editables).
- Cada una tiene su **catálogo de equipos** y **campos**, y **tarifas por posición**.
- Posiciones por defecto por liga (Central, Asistente 1, Asistente 2, Cuarto árbitro);
  **cada partido puede sobrescribirlas** (p. ej. sólo central, o con cuarto árbitro).

### 4. Jornadas y partidos
- Al crear un partido se eligen de listas: equipo local, visitante, campo; más fecha y hora.
- Asignar árbitros a cada posición requerida; modificar antes de publicar el rol.

### 5. Disponibilidad
- Por árbitro y día: **Todo el día**, **Solo de cierta hora** (rango desde–hasta) o **No disponible**, con nota.
- Avisos (no bloqueos) al asignar si el árbitro: no está disponible, tiene partidos que se cruzan
  o con menos de X minutos entre ellos (configurable), o repite en el mismo partido.

### 6. Rol para WhatsApp
- Texto con formato de WhatsApp (*negritas*, emojis) para copiar al portapapeles, legible en celular:
  liga, fecha, hora, campo, equipos y árbitros.
- Opcional: exportar como imagen PNG y abrir WhatsApp.

### 7. Cédulas
- Adjuntar PDF/JPG/PNG por partido; la app copia el archivo a su carpeta de documentos.
- Consultar por liga, jornada, fecha o partido; ver pendientes.
- Excepciones (no requiere cédula) con **motivo obligatorio**.

### 8. Pagos
- Por asignación: **Tarifa** (automática por liga y posición, editable) − **Pagado en campo**
  (lo que la liga/equipos le dan al árbitro en el campo) − **Pagos posteriores** = **Saldo pendiente**.
- Consultar lo que corresponde a cada árbitro por periodo, jornada o liga; historial.

### 9. Reportes y búsqueda
- Jornadas pasadas y futuras; buscar partidos, árbitros, cédulas y pagos.
- Reportes de asignaciones, partidos arbitrados y pagos pendientes; exportar a Excel.

### 10. Respaldos
- ZIP con base de datos y documentos; restaurar desde ZIP (con respaldo previo automático).
- Respaldo automático semanal al abrir la app.

### 11. Actualizaciones
- Al abrir, consultar si hay versión nueva (GitHub Releases); descargar e instalar fácilmente.
- Los datos viven en `%APPDATA%\Arbitros`, fuera de la carpeta del programa; respaldo antes de actualizar.

## Fases

| Fase | Contenido | Estado |
|---|---|---|
| 1 | Estructura, base de datos, login/roles, árbitros, respaldos | ✅ |
| 2 | Ligas y torneos, equipos, campos, tarifas, jornadas y partidos | Pendiente |
| 3 | Disponibilidad y asignación con avisos de conflicto | Pendiente |
| 4 | Rol para WhatsApp (texto e imagen) | Pendiente |
| 5 | Pagos, cédulas y reportes | Pendiente |
| 6 | Instalador `.exe` y auto-actualización | Pendiente |
