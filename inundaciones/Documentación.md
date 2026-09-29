# INNUVORA — Stack tecnológico y Requisitos

## 1. Stack tecnológico

- **Python:** lenguaje del backend.
- **Flask:** framework web.
- **Gunicorn:** servidor de la aplicación.
- **MySQL:** base de datos.
- **HTML, CSS y JavaScript:** interfaz web.
- **Leaflet y OpenStreetMap:** mapa interactivo.
- **API Open-Meteo:** datos de lluvia y pronóstico.
- **API INUMET:** lluvia observada (opcional).
- **Docker y Docker Compose:** despliegue.

---

## 2. Requisitos funcionales

Numerados y redactados como comportamiento del sistema. **RF-19 y RF-20 hay que implementarlos antes de la entrega**; el resto ya está en el código.

### Cuentas de usuario

- **RF-01 — Registro.** El sistema permite crear una cuenta con nombre, email y contraseña. Rechaza el registro si falta el nombre, si el email no tiene formato válido o si la contraseña tiene menos de 8 caracteres.
- **RF-02 — Email único.** El sistema impide registrar dos cuentas con el mismo email y muestra un mensaje que lo informa.
- **RF-03 — Inicio de sesión.** El sistema autentica al usuario con email y contraseña, inicia una sesión y lo redirige al mapa. Ante credenciales incorrectas muestra un mensaje de error sin indicar cuál de los dos datos falló.
- **RF-04 — Cierre de sesión.** El sistema permite cerrar la sesión y limpia sus datos.
- **RF-05 — Control de acceso.** El sistema exige sesión iniciada para consultar el mapa, el riesgo y el historial, y redirige al inicio de sesión a quien no la tenga.

### Ubicación y riesgo

- **RF-06 — Selección de ubicación.** El sistema permite elegir un departamento y ver los barrios que pertenecen a él.
- **RF-07 — Datos meteorológicos.** Para el departamento elegido, el sistema obtiene la lluvia de los últimos 3 días, la lluvia prevista para los próximos 3 días y la probabilidad máxima de precipitación.
- **RF-08 — Cálculo del riesgo.** El sistema calcula para cada barrio un porcentaje de riesgo de inundación combinando la lluvia acumulada y prevista (55 %), la probabilidad de precipitación (15 %) y el factor de terreno (30 %). El factor de terreno se obtiene de la altitud y la distancia al curso de agua; si el barrio no tiene esos datos, usa un valor neutro.
- **RF-09 — Nivel de riesgo.** El sistema clasifica el porcentaje en cuatro niveles: Bajo (menos de 25 %), Medio (25 % a menos de 50 %), Alto (50 % a menos de 75 %) y Muy alto (75 % o más).
- **RF-10 — Visualización en mapa.** El sistema muestra un mapa interactivo con un círculo por barrio, coloreado según su nivel: verde, amarillo, naranja o rojo.
- **RF-11 — Detalle por barrio.** El sistema muestra, para cada barrio, su porcentaje de riesgo y su nivel, y para el departamento la lluvia de los últimos 3 días y la prevista para los próximos 3.
- **RF-12 — Guardar mi zona.** El sistema permite marcar un barrio como "mi zona" y lo recuerda en las siguientes sesiones, mostrándolo seleccionado al abrir el mapa.
- **RF-13 — Falla del proveedor de clima.** Si no se puede obtener el pronóstico, el sistema informa que no fue posible y sugiere reintentar, sin mostrar valores inventados.
- **RF-14 — Respaldo de INUMET.** Si el proveedor configurado es INUMET y falla, el sistema usa la lluvia pasada de Open-Meteo y continúa funcionando.

### Historial y administración

- **RF-15 — Consulta de historial.** El sistema permite consultar las inundaciones registradas en un barrio, ordenadas de la más reciente a la más antigua.
- **RF-16 — Registro de inundaciones.** El sistema permite a los usuarios con rol administrador agregar un evento (barrio, fecha y descripción de hasta 255 caracteres) al historial.
- **RF-17 — Restricción de administración.** El sistema responde con acceso denegado (403) cuando un usuario sin rol administrador intenta modificar el historial.

### Alertas

- **RF-19 — Configurar alertas.** El sistema permite al usuario suscribirse a un barrio con un umbral de riesgo entre 0 y 100 %, ver sus suscripciones y eliminarlas.
- **RF-20 — Alertas activas.** El sistema muestra al usuario, al ingresar al mapa, los barrios suscritos cuyo riesgo actual supera el umbral configurado.

### Información preventiva

- **RF-18 — Recomendaciones.** La página de inicio muestra recomendaciones para antes, durante y después de una inundación, accesibles sin iniciar sesión.

### Fuera del alcance de esta entrega

El diseño contempla estas funciones, pero no están implementadas en el código actual. **No las incluyas como requisitos funcionales hasta que existan**, porque la prueba en vivo evalúa todo lo documentado.

- Gestión del perfil (editar nombre, email o contraseña).
- Envío de notificaciones por email o push (las alertas de RF-19 y RF-20 se muestran dentro de la aplicación).
- Pantalla web para que el administrador cargue el historial (hoy solo existe el endpoint).
- Carga de barrios de todo el país y de sus datos de terreno (hoy hay 6 barrios de Montevideo).

---

## 3. Requisitos no funcionales

Con criterio medible. Los marcados con (\*) son objetivos que hay que verificar antes de la entrega; el resto se cumple según el código.

### Rendimiento

- **RNF-01 — Caché del clima.** El sistema reutiliza la respuesta meteorológica de una misma ubicación durante 30 minutos, para no llamar a la API externa en cada consulta.
- **RNF-02 — Tiempo de espera.** Las llamadas a Open-Meteo tienen un tope de 8 segundos y las de INUMET de 10 segundos; pasado ese tiempo el sistema devuelve el mensaje de error de RF-13 en lugar de quedar bloqueado.
- **RNF-03 — Respuesta con caché (\*).** Con el clima en caché, la consulta de riesgo de un departamento responde en menos de 2 segundos.
- **RNF-04 — Concurrencia (\*).** El sistema atiende al menos 20 usuarios simultáneos con Gunicorn sin errores 5xx.

### Seguridad

- **RNF-05 — Contraseñas.** Las contraseñas se almacenan con hash (Werkzeug) y nunca en texto plano; la longitud mínima es de 8 caracteres.
- **RNF-06 — Inyección SQL.** El 100 % de las consultas a la base de datos usa parámetros (`%s`), sin concatenar datos del usuario.
- **RNF-07 — Sesiones.** La cookie de sesión se marca `HttpOnly` y `SameSite=Lax`.
- **RNF-08 — Secretos.** Las claves y contraseñas (`SECRET_KEY`, base de datos) se leen de variables de entorno y no están escritas en el código. El repositorio solo incluye `env.example`, con valores de ejemplo.
- **RNF-09 — Privilegios mínimos.** La aplicación corre en el contenedor con un usuario sin privilegios de administrador.
- **RNF-10 — Autorización.** El 100 % de los endpoints `/api/*` exige sesión, y los de administración exigen además rol `admin`.

### Usabilidad y accesibilidad

- **RNF-11 — Diseño adaptable.** La interfaz se adapta a pantallas de celular y de escritorio, con puntos de corte en 480, 760 y 850 px.
- **RNF-12 — Legibilidad.** El sistema usa la tipografía Atkinson Hyperlegible y ofrece modo claro y oscuro.
- **RNF-13 — Accesibilidad.** Los controles interactivos del mapa incluyen atributos ARIA (`aria-label`, `aria-live`, `aria-selected`) para lectores de pantalla.
- **RNF-14 — Idioma y lenguaje.** Toda la interfaz está en español y el nivel de riesgo se comunica con texto además de con color, para no depender solo del color.
- **RNF-15 — Pasos para consultar (\*).** Un usuario registrado llega al riesgo de su zona en no más de 3 interacciones (elegir departamento, elegir barrio, leer el resultado).

### Disponibilidad y portabilidad

- **RNF-16 — Despliegue reproducible.** El sistema completo (aplicación y base de datos) se levanta con un único comando, `docker compose up`, y crea el esquema automáticamente.
- **RNF-17 — Tolerancia a fallas externas.** Si INUMET no responde, el sistema sigue funcionando con Open-Meteo (RF-14).
- **RNF-18 — Persistencia.** Los datos de la base se guardan en un volumen de Docker y sobreviven al reinicio de los contenedores.
