-- Solo para bases YA creadas con el schema anterior (ejecutar una única vez).
-- En una base nueva no hace falta: schema.sql ya lo incluye.
--   docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < migracion_alertas.sql
SET NAMES utf8mb4;

ALTER TABLE usuarios
  ADD COLUMN alertas_email TINYINT(1) NOT NULL DEFAULT 1;

ALTER TABLE suscripciones
  ADD COLUMN ultimo_aviso DATETIME NULL,
  ADD COLUMN ultimo_nivel VARCHAR(10) NULL;

ALTER TABLE historial_inundaciones
  ADD INDEX (barrio_id, fecha);

CREATE TABLE IF NOT EXISTS notificaciones (
  id INT PRIMARY KEY AUTO_INCREMENT,
  usuario_id INT NOT NULL,
  barrio_id INT NOT NULL,
  probabilidad TINYINT UNSIGNED NOT NULL,
  nivel VARCHAR(10) NOT NULL,
  mensaje VARCHAR(400) NOT NULL,
  leida TINYINT(1) NOT NULL DEFAULT 0,
  enviada_email TINYINT(1) NOT NULL DEFAULT 0,
  creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  FOREIGN KEY (barrio_id) REFERENCES barrios(id) ON DELETE CASCADE,
  INDEX (usuario_id, creado)
);
