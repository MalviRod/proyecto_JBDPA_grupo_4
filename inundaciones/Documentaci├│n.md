# Requisitos funcionales
 
- **Registro de usuarios**
- **Inicio de sesión**
- **Gestión del perfil**
- **Selección de zonas**
- **Consultas del nivel de riesgo**
- **Mostrar mapa**
- **Información meteorológica:** qué datos se utilizan.
- **Análisis del terreno**
- **Cálculo del riesgo:** cómo se determina el riesgo en base a los datos proporcionados.
- **Visualización del riesgo:** cómo se muestra en el mapa el nivel de riesgo.
- **Notificaciones de alerta:** recibirán alertas cuando aumente el riesgo en la zona previamente seleccionada.
- **Configuración de alertas:** el usuario podrá elegir qué zonas y alertas quiere recibir.
- **Historial de inundaciones**
- **Información preventiva**
- **Administración de la plataforma:** solo gente autorizada podrá añadir o quitar información.

# Requisitos no funcionales

- **Accesibilidad**
- **Usabilidad**
- **Rendimiento**
- **Disponibilidad**
- **Precisión de los datos**
- **Actualización de la información**
- **Seguridad**
- **Privacidad de los usuarios**
- **Compatibilidad con diferentes dispositivos**
- **Confiabilidad**

# Stack tecnológico

- **Python:** lo utilizaremos para desarrollar la lógica y el funcionamiento principal del sistema.
- **Flask:** lo utilizaremos para crear y gestionar la aplicación web utilizando Python.
- **HTML:** lo utilizaremos para crear la estructura de las páginas que verá el usuario.
- **MySQL:** lo utilizaremos para almacenar los datos del sistema, como usuarios, zonas y registros.
- **API INUMET:** la utilizaremos para obtener información sobre las condiciones climáticas y las lluvias.
- **API de mapas:** la utilizaremos para incorporar el mapa interactivo de las zonas.

# Casos de uso
### Actores

- **Usuario:** se registra, inicia sesión, indica su ubicación, consulta el riesgo y configura las notificaciones.
- **Sistema:** procesa la información climática, calcula el riesgo y muestra los resultados.
- **API de clima/INUMET:** proporciona los datos necesarios sobre lluvia y condiciones climáticas.
- **API de mapas:** proporciona el mapa utilizado para visualizar las zonas según su nivel de riesgo.

| Nº   | Caso de uso                                 | Descripción                                                                                                                                    |
|------|----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------|
| CU01 | **Registrar usuario**                       | El usuario crea una cuenta ingresando sus datos.                                                                                              |
| CU02 | **Iniciar sesión**                          | El usuario ingresa sus credenciales para acceder al sistema.                                                                                  |
| CU03 | **Seleccionar ubicación**                   | El usuario selecciona el departamento y la ciudad donde vive.                                                                                 |
| CU04 | **Calcular probabilidad de lluvia**         | El sistema obtiene datos climáticos mediante la API de clima/INUMET y calcula la probabilidad de lluvia para la ubicación seleccionada.       |
| CU05 | **Consultar riesgo de inundación**          | El sistema determina el nivel de riesgo según los datos disponibles.                                                                          |
| CU06 | **Visualizar riesgo en mapa**               | El sistema utiliza la API de mapas para mostrar un mapa con diferentes colores según el nivel de riesgo: **verde, amarillo, naranja y rojo**. |
| CU07 | **Configurar notificaciones**               | El usuario decide si quiere recibir notificaciones.                                                                                           |
| CU08 | **Seleccionar lugares para notificaciones** | El usuario selecciona de qué departamentos o ciudades quiere recibir avisos.                                                                  |
| CU09 | **Recibir notificaciones**                  | El sistema envía una notificación cuando se cumplen las condiciones configuradas por el usuario.                                              |
